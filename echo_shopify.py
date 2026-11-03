"""Echo's Shopify Manager: really works on your store (Shopify Admin API).

Reads (no approval needed): products, stock, orders, low stock.
Changes (asks Yes/No on Telegram or the phone first): add a product, change a
price, set stock, edit a title/description/tags, publish/unpublish/archive,
create a discount code.

Connect once with setup_echo.bat (see SHOPIFY_SETUP.md). Settings saved in
%USERPROFILE%\\.echo_telegram.json:
  shopify_store          e.g. thedogden-2.myshopify.com
  shopify_client_id      from your app in the Shopify Dev Dashboard
  shopify_client_secret  (Echo swaps these for a 24-hour token by itself)
  shopify_token          OR a ready-made Admin API token (shpat_...) instead
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"
DIR = Path.home() / "Echo_business"
PENDING = DIR / "shopify_pending.json"
TOKEN_CACHE = Path.home() / ".echo_shopify_token.json"
LOG = DIR / "shopify_log.json"
API_VERSION = os.getenv("ECHO_SHOPIFY_API_VERSION", "2025-10")
PENDING_MINUTES = 120
SCOPES = ("read_products, write_products, read_inventory, write_inventory, read_locations, "
          "read_orders, read_discounts, write_discounts, read_publications, write_publications")


# ==========================================
# CONNECTION
# ==========================================

def _settings():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    get = lambda k, env: (os.getenv(env) or str(data.get(k, ""))).strip()
    store = get("shopify_store", "SHOPIFY_STORE").replace("https://", "").replace("http://", "").strip("/")
    if store and "." not in store:
        store += ".myshopify.com"
    return {"store": store, "token": get("shopify_token", "SHOPIFY_TOKEN"),
            "client_id": get("shopify_client_id", "SHOPIFY_CLIENT_ID"),
            "client_secret": get("shopify_client_secret", "SHOPIFY_CLIENT_SECRET")}


def is_configured():
    s = _settings()
    return bool(s["store"] and (s["token"] or (s["client_id"] and s["client_secret"])))


NOT_CONNECTED = ("I'm not connected to your Shopify store yet, so I can't change anything there. "
                 "It's a one-time setup (about 5 minutes): follow SHOPIFY_SETUP.md, then double-click "
                 "connect_echo.bat and paste in your store address, Client ID and Client secret.")


def _token(force=False):
    s = _settings()
    if s["token"]:
        return s["token"]
    if not force:
        try:
            c = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
            if c.get("store") == s["store"] and c.get("expires", 0) > time.time() + 120:
                return c["token"]
        except (OSError, ValueError, KeyError):
            pass
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": s["client_id"],
                                   "client_secret": s["client_secret"]}).encode()
    req = urllib.request.Request(f"https://{s['store']}/admin/oauth/access_token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        hint = (" The app must be installed on this store (Dev Dashboard > your app > Install)."
                if "shop_not_permitted" in detail or exc.code in (400, 401, 403) else "")
        raise RuntimeError(f"Shopify wouldn't give Echo a key ({exc.code}): {detail}.{hint}") from None
    except urllib.error.URLError:
        raise RuntimeError("Couldn't reach Shopify. Check the internet connection.") from None
    token = data["access_token"]
    TOKEN_CACHE.write_text(json.dumps({"store": s["store"], "token": token,
                                       "expires": time.time() + int(data.get("expires_in", 86399))}),
                           encoding="utf-8")
    return token


def gql(query, variables=None, _retry=True):
    if not is_configured():
        raise RuntimeError(NOT_CONNECTED)
    s = _settings()
    req = urllib.request.Request(
        f"https://{s['store']}/admin/api/{API_VERSION}/graphql.json",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": _token()})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and _retry and not s["token"]:
            _token(force=True)
            return gql(query, variables, _retry=False)
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Shopify said no ({exc.code}): {detail}") from None
    except urllib.error.URLError:
        raise RuntimeError("Couldn't reach Shopify. Check the internet connection.") from None
    if data.get("errors"):
        msg = "; ".join(e.get("message", "") for e in data["errors"])[:300]
        if "access" in msg.lower() or "scope" in msg.lower():
            msg += f" (Echo's app needs these scopes: {SCOPES})"
        raise RuntimeError("Shopify error: " + msg)
    return data["data"]


def _errors(payload):
    errs = payload.get("userErrors") or []
    if errs:
        raise RuntimeError("Shopify didn't accept that: " + "; ".join(
            f"{'/'.join(map(str, e.get('field') or []))} {e.get('message', '')}".strip() for e in errs))


def test():
    """Check the connection. Returns a one-line status."""
    d = gql("{ shop { name myshopifyDomain currencyCode } productsCount { count } }")
    return (f"Connected to {d['shop']['name'].strip()} ({d['shop']['myshopifyDomain']}), "
            f"{d['productsCount']['count']} products, prices in {d['shop']['currencyCode']}.")


# ==========================================
# READING THE STORE
# ==========================================

PRODUCT_FIELDS = """id title handle status totalInventory tags
  variants(first: 10) { nodes { id title price sku inventoryQuantity inventoryItem { id } } }"""


def products(search="", limit=15):
    d = gql("query($q: String, $n: Int!) { products(first: $n, query: $q, sortKey: UPDATED_AT, reverse: true) "
            "{ nodes { " + PRODUCT_FIELDS + " } } }", {"q": search or None, "n": limit})
    return d["products"]["nodes"]


def find_product(name):
    """Best match for a product name (exact title first)."""
    name = name.strip().strip("'\"")
    found = products(f'title:*{name}*', 10) or products(name, 10)
    for p in found:
        if p["title"].lower() == name.lower():
            return p
    return found[0] if found else None


def product_list(search=""):
    ps = products(search, 20)
    if not ps:
        return "No products found." if search else "Your store has no products yet. Tell me what to add!"
    lines = [f"🛍️ {'Products matching ' + repr(search) if search else 'Your products'} ({len(ps)}):"]
    for p in ps:
        v = p["variants"]["nodes"][0] if p["variants"]["nodes"] else {}
        lines.append(f"• {p['title']}: ${float(v.get('price') or 0):,.2f}, stock {p['totalInventory']}"
                     f"{'' if p['status'] == 'ACTIVE' else ' (' + p['status'].lower() + ')'}")
    return "\n".join(lines)


def low_stock(threshold=5):
    ps = [p for p in products("", 100) if p["totalInventory"] is not None and p["totalInventory"] <= threshold
          and p["status"] == "ACTIVE"]
    if not ps:
        return f"Nothing is low on stock (all active products have more than {threshold})."
    return "⚠️ Low stock:\n" + "\n".join(f"• {p['title']}: {p['totalInventory']} left" for p in ps)


def orders(limit=10):
    d = gql("query($n: Int!) { orders(first: $n, sortKey: CREATED_AT, reverse: true) { nodes { name createdAt "
            "displayFinancialStatus displayFulfillmentStatus totalPriceSet { shopMoney { amount currencyCode } } "
            "lineItems(first: 5) { nodes { title quantity } } } } }", {"n": limit})
    os_ = d["orders"]["nodes"]
    if not os_:
        return "No orders yet."
    lines = ["🧾 Latest orders:"]
    for o in os_:
        m = o["totalPriceSet"]["shopMoney"]
        items = ", ".join(f"{li['quantity']}× {li['title']}" for li in o["lineItems"]["nodes"])
        lines.append(f"• {o['name']} {o['createdAt'][:10]}: ${float(m['amount']):,.2f} {m['currencyCode']} "
                     f"({o['displayFinancialStatus'].lower()}, {(o['displayFulfillmentStatus'] or '').lower()}) - {items}")
    return "\n".join(lines)


def _location_id():
    return gql("{ locations(first: 1) { nodes { id } } }")["locations"]["nodes"][0]["id"]


# ==========================================
# CHANGING THE STORE (only run after your Yes)
# ==========================================

def _upload_image(path):
    """Upload a local picture to Shopify; returns a URL Shopify can use for product media."""
    path = Path(path)
    mime = {".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}.get(path.suffix.lower(), "image/jpeg")
    d = gql("mutation($i: [StagedUploadInput!]!) { stagedUploadsCreate(input: $i) { stagedTargets "
            "{ url resourceUrl parameters { name value } } userErrors { field message } } }",
            {"i": [{"filename": path.name, "mimeType": mime, "resource": "IMAGE", "httpMethod": "POST",
                    "fileSize": str(path.stat().st_size)}]})["stagedUploadsCreate"]
    _errors(d)
    t = d["stagedTargets"][0]
    boundary = "Echo" + uuid.uuid4().hex
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{p["name"]}"\r\n\r\n{p["value"]}\r\n'.encode()
             for p in t["parameters"]]
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                  f"Content-Type: {mime}\r\n\r\n").encode() + path.read_bytes() + b"\r\n")
    req = urllib.request.Request(t["url"], data=b"".join(parts) + f"--{boundary}--\r\n".encode(),
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=120):
        pass
    return t["resourceUrl"]


def create_product(title, price, description="", stock=None, tags=None, product_type="", vendor="",
                   status="ACTIVE", images=None, compare_at=None, sku=""):
    media = []
    for img in images or []:
        src = img if str(img).startswith("http") else _upload_image(img)
        media.append({"originalSource": src, "mediaContentType": "IMAGE", "alt": title})
    product = {"title": title, "descriptionHtml": description, "status": status}
    if tags:
        product["tags"] = tags
    if product_type:
        product["productType"] = product_type
    if vendor:
        product["vendor"] = vendor
    d = gql("mutation($p: ProductCreateInput!, $m: [CreateMediaInput!]) { productCreate(product: $p, media: $m) "
            "{ product { id handle title variants(first: 1) { nodes { id inventoryItem { id } } } } "
            "userErrors { field message } } }", {"p": product, "m": media or None})["productCreate"]
    _errors(d)
    p = d["product"]
    v = p["variants"]["nodes"][0]
    variant = {"id": v["id"], "price": f"{float(price):.2f}",
               "inventoryItem": {"tracked": stock is not None, **({"sku": sku} if sku else {})}}
    if compare_at:
        variant["compareAtPrice"] = f"{float(compare_at):.2f}"
    u = gql("mutation($id: ID!, $v: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $id, "
            "variants: $v) { userErrors { field message } } }", {"id": p["id"], "v": [variant]})
    _errors(u["productVariantsBulkUpdate"])
    if stock is not None:
        _set_qty(v["inventoryItem"]["id"], int(stock))
    if status == "ACTIVE":
        _publish(p["id"])
    s = _settings()["store"]
    return (f"✅ Added '{p['title']}' at ${float(price):,.2f}" + (f", stock {stock}" if stock is not None else "") +
            f".\nAdmin: https://{s}/admin/products/{p['id'].rsplit('/', 1)[-1]}")


def _publish(product_id):
    """Put the product on the Online Store sales channel (ignored if the scope isn't granted)."""
    try:
        pubs = gql("{ publications(first: 10) { nodes { id name } } }")["publications"]["nodes"]
        for pub in pubs:
            if "online store" in pub["name"].lower():
                gql("mutation($id: ID!, $p: [PublicationInput!]!) { publishablePublish(id: $id, input: $p) "
                    "{ userErrors { message } } }", {"id": product_id, "p": [{"publicationId": pub["id"]}]})
    except RuntimeError:
        pass


def _set_qty(inventory_item_id, qty):
    loc = _location_id()
    try:
        gql("mutation($i: ID!, $l: ID!) { inventoryActivate(inventoryItemId: $i, locationId: $l) "
            "{ userErrors { message } } }", {"i": inventory_item_id, "l": loc})
    except RuntimeError:
        pass
    gql("mutation($i: ID!) { inventoryItemUpdate(id: $i, input: {tracked: true}) { userErrors { message } } }",
        {"i": inventory_item_id})
    d = gql("mutation($in: InventorySetQuantitiesInput!) { inventorySetQuantities(input: $in) "
            "{ userErrors { field message } } }",
            {"in": {"name": "available", "reason": "correction", "ignoreCompareQuantity": True,
                    "quantities": [{"inventoryItemId": inventory_item_id, "locationId": loc, "quantity": qty}]}})
    _errors(d["inventorySetQuantities"])


def _need(name):
    p = find_product(name)
    if not p:
        raise RuntimeError(f"I couldn't find a product called '{name}' in your store.")
    return p


def set_price(name, price, compare_at=None):
    p = _need(name)
    vs = [{"id": v["id"], "price": f"{float(price):.2f}",
           **({"compareAtPrice": f"{float(compare_at):.2f}"} if compare_at else {})} for v in p["variants"]["nodes"]]
    d = gql("mutation($id: ID!, $v: [ProductVariantsBulkInput!]!) { productVariantsBulkUpdate(productId: $id, "
            "variants: $v) { userErrors { field message } } }", {"id": p["id"], "v": vs})
    _errors(d["productVariantsBulkUpdate"])
    return f"✅ '{p['title']}' is now ${float(price):,.2f}" + (f" (was ${float(compare_at):,.2f})" if compare_at else "") + "."


def set_stock(name, qty):
    p = _need(name)
    _set_qty(p["variants"]["nodes"][0]["inventoryItem"]["id"], int(qty))
    return f"✅ '{p['title']}' stock set to {int(qty)}."


def update_product(name, title=None, description=None, tags=None, status=None):
    p = _need(name)
    fields = {"id": p["id"]}
    if title:
        fields["title"] = title
    if description:
        fields["descriptionHtml"] = description
    if tags:
        fields["tags"] = tags
    if status:
        fields["status"] = status
    d = gql("mutation($p: ProductUpdateInput!) { productUpdate(product: $p) { product { title status } "
            "userErrors { field message } } }", {"p": fields})["productUpdate"]
    _errors(d)
    if status == "ACTIVE":
        _publish(p["id"])
    return f"✅ Updated '{d['product']['title']}' ({d['product']['status'].lower()})."


def create_discount(code, percent=None, amount=None, days=30):
    value = ({"percentage": float(percent) / 100} if percent else
             {"discountAmount": {"amount": f"{float(amount):.2f}", "appliesOnEachItem": False}})
    now = datetime.now(timezone.utc)
    d = gql("mutation($d: DiscountCodeBasicInput!) { discountCodeBasicCreate(basicCodeDiscount: $d) "
            "{ userErrors { field message } } }", {"d": {
                "title": code, "code": code, "startsAt": now.isoformat(),
                "endsAt": datetime.fromtimestamp(now.timestamp() + days * 86400, timezone.utc).isoformat(),
                "customerSelection": {"all": True}, "appliesOncePerCustomer": False,
                "customerGets": {"value": value, "items": {"all": True}}}})
    _errors(d["discountCodeBasicCreate"])
    return f"✅ Discount code {code} is live: {f'{percent:g}% off' if percent else f'${float(amount):,.2f} off'} for {days} days."


ACTIONS = {"create_product": create_product, "set_price": set_price, "set_stock": set_stock,
           "update_product": update_product, "create_discount": create_discount}


# ==========================================
# UNDERSTANDING WHAT YOU ASK
# ==========================================

PARSE_PROMPT = """Turn the user's request about their Shopify store into ONE JSON object, nothing else.
Pick one "action":
- "create_product": {"title", "price" (number), "description" (2-4 sentence selling description in HTML <p> tags; write one if not given), "stock" (number or null), "tags" (list), "product_type", "status" ("ACTIVE" or "DRAFT"; DRAFT only if they say draft), "compare_at" (number or null)}
- "set_price": {"name" (existing product), "price", "compare_at" (old price for a sale, or null)}
- "set_stock": {"name", "qty"}
- "update_product": {"name", "title" (new title or null), "description" (or null), "tags" (or null), "status" ("ACTIVE", "DRAFT", "ARCHIVED" or null)}
- "create_discount": {"code" (UPPERCASE, no spaces), "percent" (or null), "amount" (or null), "days"}
- "list_products": {"search"}
- "orders": {}
- "low_stock": {}
- "unclear": {"question": what you need to ask them}
Put the fields next to "action" in the same object. Prices are in AUD. Never invent a price: if adding a product without a price, use "unclear" and ask for it.
Request: """

STORE_WORDS = re.compile(r"\b(shopify|store|shop|product|products|listing|listings|stock|inventory|orders?|"
                         r"discount|coupon|price|prices|sale|furventure)\b", re.I)


def parse(text):
    from echo_business import ask_ai
    raw = ask_ai(PARSE_PROMPT + text, system="You output only valid JSON.", timeout=180)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"action": "unclear", "question": "Sorry, what exactly should I change in the store?"}
    try:
        return json.loads(m.group(0))
    except ValueError:
        return {"action": "unclear", "question": "Sorry, I didn't catch that. What should I change in the store?"}


def _quick(text):
    """Common requests without needing the AI."""
    low = text.lower().strip()
    if re.search(r"\b(orders?|sales today|what sold)\b", low) and not re.search(r"\b(add|create|change|set)\b", low):
        return {"action": "orders"}
    if re.search(r"\b(low stock|running out|out of stock)\b", low):
        return {"action": "low_stock"}
    if re.search(r"^(?:/shop(?:ify)?|/products|(?:show|list|what are)(?: me)? (?:my |the )?products)\s*$", low):
        return {"action": "list_products", "search": ""}
    m = re.search(r"\b(?:price of|change|set|make)\s+(.+?)\s+(?:price\s+)?(?:to|at)\s+\$?([\d.]+)\b", text, re.I)
    if m and not re.search(r"\b(stock|inventory|qty|quantity)\b", low):
        return {"action": "set_price", "name": re.sub(r"\s+price$", "", m.group(1), flags=re.I), "price": float(m.group(2))}
    m = re.search(r"\b(?:set|change|update)\s+(?:the\s+)?(?:stock|inventory)\s+(?:of|for)\s+(.+?)\s+to\s+(\d+)\b", text, re.I)
    if m:
        return {"action": "set_stock", "name": m.group(1), "qty": int(m.group(2))}
    return None


def describe(plan):
    a = plan["action"]
    if a == "create_product":
        return "\n".join(x for x in [
            f"ADD PRODUCT: {plan.get('title')}",
            f"Price ${float(plan.get('price') or 0):,.2f}" + (f" (was ${float(plan['compare_at']):,.2f})" if plan.get("compare_at") else "") +
            (f" · stock {plan['stock']}" if plan.get("stock") is not None else " · stock not tracked"),
            "Status: " + ("live on your store" if plan.get("status", "ACTIVE") == "ACTIVE" else "draft (hidden)"),
            ("Tags: " + ", ".join(plan["tags"])) if plan.get("tags") else "",
            ("Photo: " + str(len(plan["images"])) + " attached") if plan.get("images") else "",
            "Description: " + re.sub(r"<[^>]+>", " ", plan.get("description") or "").strip()[:400]] if x)
    if a == "set_price":
        return f"CHANGE PRICE: {plan['name']} → ${float(plan['price']):,.2f}" + (
            f" (showing was ${float(plan['compare_at']):,.2f})" if plan.get("compare_at") else "")
    if a == "set_stock":
        return f"SET STOCK: {plan['name']} → {plan['qty']}"
    if a == "update_product":
        bits = [f"title → {plan['title']}" if plan.get("title") else "", "new description" if plan.get("description") else "",
                f"tags → {', '.join(plan['tags'])}" if plan.get("tags") else "",
                f"status → {plan['status'].lower()}" if plan.get("status") else ""]
        return f"UPDATE PRODUCT: {plan['name']}: " + ", ".join(b for b in bits if b)
    if a == "create_discount":
        return (f"CREATE DISCOUNT CODE {plan['code']}: " +
                (f"{float(plan['percent']):g}% off" if plan.get("percent") else f"${float(plan.get('amount') or 0):,.2f} off") +
                f" everything, for {plan.get('days') or 30} days")
    return a


def _clean(plan):
    a = plan.get("action")
    keep = {"create_product": ("title", "price", "description", "stock", "tags", "product_type", "status",
                               "compare_at", "images", "sku"),
            "set_price": ("name", "price", "compare_at"), "set_stock": ("name", "qty"),
            "update_product": ("name", "title", "description", "tags", "status"),
            "create_discount": ("code", "percent", "amount", "days")}[a]
    out = {k: plan[k] for k in keep if plan.get(k) not in (None, "", [])}
    if a == "create_product":
        out["status"] = "DRAFT" if str(out.get("status", "")).upper() == "DRAFT" else "ACTIVE"
        if isinstance(out.get("tags"), str):
            out["tags"] = [t.strip() for t in out["tags"].split(",") if t.strip()]
    if a == "update_product" and out.get("status"):
        out["status"] = str(out["status"]).upper()
    if a == "create_discount":
        out["code"] = re.sub(r"[^A-Z0-9]", "", str(out.get("code", "SAVE")).upper()) or "SAVE10"
        out["days"] = int(out.get("days") or 30)
    return out


# ==========================================
# APPROVAL (Yes/No on Telegram or the phone)
# ==========================================

def propose(plan):
    DIR.mkdir(parents=True, exist_ok=True)
    plan["created"] = datetime.now(timezone.utc).isoformat()
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    msg = "🛍️ Shopify Manager wants to:\n" + describe(plan) + "\n\nReply Yes to do it, or No to cancel."
    sent = False
    try:
        from echo_telegram import YES_NO_KEYBOARD, chat_bot_credentials
        token, chat = chat_bot_credentials()
        if token and chat:
            req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                         data=urllib.parse.urlencode({"chat_id": chat, "text": msg[:4000],
                                                                      "reply_markup": YES_NO_KEYBOARD}).encode())
            with urllib.request.urlopen(req, timeout=30) as r:
                sent = json.load(r).get("ok", False)
    except Exception:
        pass
    return msg, sent


def pending():
    try:
        plan = json.loads(PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(plan["created"])).total_seconds()
    if age > PENDING_MINUTES * 60:
        PENDING.unlink(missing_ok=True)
        return None
    return plan


def skip():
    PENDING.unlink(missing_ok=True)
    return "OK, cancelled. Nothing changed in the store."


def approve():
    plan = pending()
    if not plan:
        return "That store change has expired or was already done. Nothing changed."
    PENDING.unlink(missing_ok=True)
    action = plan.pop("action")
    plan.pop("created", None)
    result = ACTIONS[action](**plan)
    _log(action, plan, result)
    try:
        from echo_business import record
        record("Shopify Manager", result.splitlines()[0].replace("✅ ", ""))
    except Exception:
        pass
    return result


def _log(action, plan, result):
    try:
        log = json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = []
    log.append({"at": datetime.now().isoformat(timespec="seconds"), "action": action,
                "plan": {k: v for k, v in plan.items() if k != "description"}, "result": result})
    DIR.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log[-200:], indent=2), encoding="utf-8")


def recent_changes(n=5):
    try:
        return json.loads(LOG.read_text(encoding="utf-8"))[-n:]
    except (OSError, ValueError):
        return []


# ==========================================
# ENTRY POINT
# ==========================================

def handle(text, images=None, force=False):
    """Do a store request. Returns a reply, or None if it isn't about the store.
    force=True when you're talking to the Shopify Manager directly."""
    if not force and not STORE_WORDS.search(text):
        return None
    if not is_configured():
        return NOT_CONNECTED
    try:
        plan = _quick(text) or parse(text)
        a = plan.get("action")
        if a == "list_products":
            return product_list(plan.get("search") or "")
        if a == "orders":
            return orders()
        if a == "low_stock":
            return low_stock()
        if a not in ACTIONS:
            return plan.get("question") or "What would you like me to change in the store?"
        plan = {"action": a, **_clean(plan)}
        if a == "create_product":
            if not plan.get("title") or not plan.get("price"):
                return "What should the product be called, and what price (AUD)?"
            if images:
                plan["images"] = [str(p) for p in images]
        elif a != "create_discount":
            found = find_product(plan.get("name", ""))
            if not found:
                return f"I couldn't find '{plan.get('name')}' in your store. Say 'show my products' to see them."
            plan["name"] = found["title"]
        msg, sent = propose(plan)
        return (msg.split("\n\n")[0] + ("\n\nI've sent this to your phone: tap ✅ Yes on Telegram and I'll do it." if sent
                else "\n\nReply Yes on Telegram to do it (Telegram isn't connected, so I couldn't send it there)."))
    except RuntimeError as exc:
        return str(exc)
    except Exception as exc:
        return "Something went wrong talking to the store: " + type(exc).__name__ + ": " + str(exc)[:200]


if __name__ == "__main__":
    print(test() if is_configured() else NOT_CONNECTED)
