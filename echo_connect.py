"""Connect Echo's offices to your real accounts from your phone: /connect on Telegram.

    /connect            what's connected (🟢) and what isn't (🔴), numbered
    /connect 1          step-by-step for that account: Echo sends the links, you paste each key here
    cancel              stop

Each key you paste is saved on the PC (in .echo_telegram.json, the same place connect_echo.bat uses),
your message is deleted from the chat straight away, and Echo tests the connection and tells you if
it worked. Keys are never written to Echo's memory, logs or GitHub.
Note: Telegram chats with bots aren't end-to-end encrypted, so connect_echo.bat on the PC is still the
most private way. This is the convenient way from your phone.
"""
import json
import re
import time
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"
STATE = Path.home() / ".echo_connect_state.json"
TIMEOUT_MIN = 30

# key, office, what it unlocks, steps, fields [(setting, question, check regex, help when wrong)], test
SERVICES = [
    {"key": "opusclip", "name": "OpusClip → YouTube, TikTok, Instagram",
     "office": "Content Creator",
     "unlocks": "makes clips from videos and posts them to your YouTube, TikTok and Instagram (after your Yes)",
     "steps": ["Open clip.opus.pro on your phone and log in.",
               "Tap the menu, then 'API' (bottom-left on a computer) and copy your API key."],
     "fields": [("opusclip_api_key", "Paste your OpusClip API key", r"^\S{16,}$", "That doesn't look like an API key.")]},
    {"key": "shopify", "name": "Shopify (Furventure)",
     "office": "Shopify Manager",
     "unlocks": "reads orders and stock, adds products, changes prices, makes discount codes (after your Yes)",
     "steps": ["Open dev.shopify.com/dashboard and log in with your Shopify account.",
               "Tap 'Create app', name it Echo. Create a version: under Access → Scopes tick read and write for "
               "products, inventory, orders, discounts and publications, plus read_locations. Tap Release.",
               "Tap 'Install app' and choose Furventure.",
               "Open the app's Settings: you'll copy the Client ID and Client secret from there."],
     "fields": [("shopify_store", "Your store address (reply 'ok' for thedogden-2.myshopify.com)",
                 r"^[a-z0-9-]+(\.myshopify\.com)?$", "Send just the store address, e.g. thedogden-2.myshopify.com"),
                ("shopify_client_id", "Paste the Client ID", r"^[A-Za-z0-9]{16,}$", "That doesn't look like a Client ID."),
                ("shopify_client_secret", "Paste the Client secret", r"^\S{16,}$", "That doesn't look like a Client secret.")]},
    {"key": "gmail", "name": "Gmail",
     "office": "Sales Agent + Customer Support",
     "unlocks": "sends your pitches and replies from your Gmail (you see each email and tap Yes first)",
     "steps": ["Your Google account needs 2-Step Verification on (myaccount.google.com/security).",
               "Open myaccount.google.com/apppasswords, type 'Echo' and tap Create.",
               "Copy the 16-letter password Google shows."],
     "fields": [("gmail_address", "Your Gmail address", r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", "Send your full Gmail address."),
                ("gmail_app_password", "Paste the 16-letter app password", r"^[a-z]{16}$",
                 "App passwords are 16 letters (spaces don't matter).")]},
    {"key": "alpaca", "name": "Alpaca (trading, practice money first)",
     "office": "Day Trading Desk",
     "unlocks": "places trades you approve, with a stop-loss and target on each (practice account by default)",
     "steps": ["Sign up free at alpaca.markets and open the Paper Trading account.",
               "On the dashboard, find 'API Keys' and tap Generate. Copy the Key ID and Secret."],
     "fields": [("alpaca_key_id", "Paste the Key ID", r"^[A-Z0-9]{16,}$", "That doesn't look like an Alpaca Key ID."),
                ("alpaca_secret_key", "Paste the Secret key", r"^\S{20,}$", "That doesn't look like an Alpaca secret.")]},
]


def _cfg():
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_setting(key, value):
    d = _cfg()
    d[key] = value
    CONFIG.write_text(json.dumps(d, indent=2), encoding="utf-8")


def _state():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if time.time() - s.get("at", 0) > TIMEOUT_MIN * 60:
        STATE.unlink(missing_ok=True)
        return {}
    return s


def _set_state(s):
    if s:
        s["at"] = time.time()
        STATE.write_text(json.dumps(s), encoding="utf-8")
    else:
        STATE.unlink(missing_ok=True)


def active():
    return bool(_state())


def _connected(svc):
    d = _cfg()
    return all(str(d.get(f[0], "")).strip() for f in svc["fields"])


def _test(svc):
    """Real login test. Returns (ok, text)."""
    try:
        if svc["key"] == "opusclip":
            import echo_opusclip
            return True, echo_opusclip.test()
        if svc["key"] == "shopify":
            import echo_shopify
            return True, echo_shopify.test()
        if svc["key"] == "gmail":
            import echo_email
            return True, echo_email.test()
        if svc["key"] == "alpaca":
            import echo_broker
            a = echo_broker.account()
            return True, f"Account ready ({echo_broker.mode()}), equity ${a['equity']:,.2f}"
    except Exception as exc:
        return False, str(exc)[:250]
    return True, ""


def menu():
    lines = ["🔌 Connect Echo's offices to your accounts. Reply /connect and a number:"]
    for i, svc in enumerate(SERVICES, 1):
        tick = "🟢" if _connected(svc) else "🔴"
        lines.append(f"{tick} {i}. {svc['name']}: {svc['office']} {svc['unlocks']}")
    lines += ["", "Already free, nothing to connect: YouTube video search, lead finding, research, Brand Studio, "
              "the CEO plan, backups.",
              "Your keys are saved on the PC and your message is deleted from this chat straight away. "
              "Most private alternative: connect_echo.bat on the PC."]
    return "\n".join(lines)


def _ask(svc, i):
    question = svc["fields"][i][1]
    return f"({i + 1}/{len(svc['fields'])}) {question}. Or 'cancel'."


def start(n):
    if not 1 <= n <= len(SERVICES):
        return menu()
    svc = SERVICES[n - 1]
    _set_state({"svc": svc["key"], "field": 0})
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(svc["steps"], 1))
    return (f"🔌 Connecting {svc['name']} so the {svc['office']} {svc['unlocks']}.\n\n{steps}\n\n" + _ask(svc, 0))


def answer(text):
    """The next pasted value. Returns (reply, delete_message?)."""
    s = _state()
    if not s:
        return None, False
    if re.match(r"^\s*(cancel|stop|quit)\s*$", text, re.I):
        _set_state({})
        return "Stopped. Nothing else was changed. /connect to start again.", False
    svc = next(x for x in SERVICES if x["key"] == s["svc"])
    setting, _q, pattern, wrong = svc["fields"][s["field"]]
    value = text.strip()
    if setting == "shopify_store" and value.lower() in ("ok", "yes", "y"):
        value = "thedogden-2.myshopify.com"
    if setting == "gmail_app_password":
        value = value.replace(" ", "").lower()
    if setting == "shopify_store":
        value = value.lower().replace("https://", "").replace("http://", "").strip("/")
    check = value.replace(".myshopify.com", "") if setting == "shopify_store" else value
    if not re.match(pattern, check if setting == "shopify_store" else value, re.I):
        return f"{wrong} {_ask(svc, s['field'])}", True
    if setting == "shopify_store" and "." not in value:
        value += ".myshopify.com"
    _save_setting(setting, value)
    s["field"] += 1
    if s["field"] < len(svc["fields"]):
        _set_state(s)
        return "✅ Saved (your message was deleted). " + _ask(svc, s["field"]), True
    _set_state({})
    ok, detail = _test(svc)
    if ok:
        return (f"🟢 {svc['name']} is connected and working. {detail}\nThe {svc['office']} now {svc['unlocks']}. "
                "/connect for the next one."), True
    return (f"🔴 Saved, but the test didn't work: {detail}\nCheck the steps and send /connect "
            f"{SERVICES.index(svc) + 1} to try again."), True


def handle(text):
    """Telegram: returns (reply, delete_message?) or None if the message isn't for /connect."""
    t = text.strip()
    if active() and not t.startswith("/"):
        return answer(t)
    m = re.match(r"^/connect(?:\s+(\d))?\s*$", t, re.I)
    if m:
        return (start(int(m.group(1))) if m.group(1) else menu()), False
    m = re.match(r"^/?connect\s+(opus\s?clip|shopify|gmail|email|alpaca|trading)\b", t, re.I)
    if m:
        name = m.group(1).lower().replace(" ", "")
        key = {"opusclip": "opusclip", "email": "gmail", "trading": "alpaca"}.get(name, name)
        return start(next(i for i, x in enumerate(SERVICES, 1) if x["key"] == key)), False
    return None


_SECRET_LIKE = re.compile(r"(shpat_|shpss_|sk-|AKIA|\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|"
                          r"^[A-Za-z0-9_\-]{28,}$|^(?:[a-z]{4}\s){3}[a-z]{4}$)")


def looks_like_secret(text):
    """A message that looks like a key or password, so it must never go to the AI or its memory."""
    return bool(_SECRET_LIKE.search((text or "").strip()))
