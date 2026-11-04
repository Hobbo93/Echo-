"""Website sales machine: everything you need to sell a website to a local business.

    sell Joe's Barbers            pitch drafts (text, email, phone opener) + a free preview website
                                  of THEIR business, sent to your phone to show them
    preview Joe's Barbers         just the preview website
    my website price is $499      Echo puts your price in every pitch
    /sales                        scoreboard: who's new, contacted, said yes, said no
    mark Joe's Barbers won        (as before) move a business along the pipeline

Every morning at 9 AM, Echo reminds you who's due a follow-up, and each Monday it sends the
sales scoreboard. Echo never contacts businesses itself: you send the messages. Free.
"""
import base64
import hashlib
import html
import json
import re
from datetime import date
from pathlib import Path

import echo_business
import echo_log

THEMES = [  # (words in the business type, accent colour, dark colour)
    (r"cafe|coffee|bakery|restaurant|food|pizza|takeaway|fast food|deli|butcher", "#e8833a", "#2b1a10"),
    (r"hair|barber|beauty|nail|salon|massage|tattoo|spa", "#c2569b", "#24121f"),
    (r"electric|plumb|build|carpent|paint|roof|tile|repair|tyre|mechanic|garden|hardware", "#2f7de1", "#0f1a2b"),
    (r"pet|vet|dog|groom", "#2fa36b", "#0f2419"),
    (r"dent|doctor|clinic|health|physio", "#1aa3b8", "#0d2226"),
]
SERVICES = [
    (r"cafe|coffee", ["Barista coffee", "Breakfast & brunch", "Fresh cakes & pastries", "Takeaway & catering"]),
    (r"bakery", ["Fresh bread daily", "Cakes & pastries", "Custom celebration cakes", "Catering orders"]),
    (r"restaurant|pizza|food|takeaway|deli", ["Dine in", "Takeaway", "Family meals", "Catering & functions"]),
    (r"barber", ["Haircuts", "Skin fades", "Beard trims", "Kids' cuts"]),
    (r"hair|salon", ["Cuts & styling", "Colour & foils", "Treatments", "Wedding & event hair"]),
    (r"beauty|nail|spa|massage", ["Nails", "Facials & skin", "Waxing & brows", "Massage & relaxation"]),
    (r"electric", ["Repairs & fault finding", "Lighting & power points", "Switchboard upgrades", "Safety checks"]),
    (r"plumb", ["Blocked drains", "Hot water", "Leaks & repairs", "Bathroom & kitchen plumbing"]),
    (r"mechanic|repair|tyre", ["Servicing", "Repairs", "Tyres & wheel alignment", "Roadworthy checks"]),
    (r"pet|groom|dog", ["Grooming", "Wash & tidy", "Nail clips", "Puppy care"]),
]


def _theme(category):
    for pattern, accent, dark in THEMES:
        if re.search(pattern, category or "", re.I):
            return accent, dark
    h = int(hashlib.md5((category or "x").encode()).hexdigest()[:6], 16)
    return f"#{(h & 0x7f7f7f) + 0x404040:06x}", "#121826"


def _default_services(category):
    for pattern, items in SERVICES:
        if re.search(pattern, category or "", re.I):
            return items
    return ["Friendly local service", "Fair prices", "Quality work", "Call for a quote"]


# ==========================================
# FINDING THE BUSINESS
# ==========================================

def find_lead(name):
    """Full details for a business: the newest saved lead list first, then the pipeline."""
    want = (name or "").lower().strip()
    if not want:
        return None
    try:
        import echo_leads
        days = sorted((p for p in echo_leads.LEADS_DIR.iterdir() if (p / "leads.json").is_file()), reverse=True) \
            if echo_leads.LEADS_DIR.is_dir() else []
        for day in days:
            for lead in json.loads((day / "leads.json").read_text(encoding="utf-8")).get("all_leads", []):
                if want in lead["name"].lower():
                    return lead
    except Exception as exc:
        echo_log.error("sales find_lead", exc)
    _key, lead = echo_business._find(echo_business._pipeline(), want)
    return lead


# ==========================================
# PREVIEW WEBSITE
# ==========================================

def _copy(lead, ask=None):
    """Tagline, about and services for the preview (local AI, with sensible defaults if it's off)."""
    parts = [x.strip() for x in (lead.get("address") or "").split(",") if x.strip() and x.strip() != "SA"]
    suburb = re.sub(r"\s+(SA|South Australia)\b.*$", "", parts[-1]) if parts else "Adelaide"
    defaults = {"tagline": f"Your local {(lead.get('category') or 'business').lower()} in {suburb}",
                "about": f"{lead['name']} is a friendly, locally owned business serving the community. "
                         "Drop in, or call us today.",
                "services": _default_services(lead.get("category", ""))}
    prompt = ("Write website copy for a small local business. Only use the facts given; don't invent awards, "
              "years, prices or staff names. Answer with ONLY JSON: {\"tagline\": max 8 words, \"about\": 2 short "
              "sentences, \"services\": 4 short service names}.\n"
              f"Business: {lead['name']}. Type: {lead.get('category')}. Area: {lead.get('address')}.")
    try:
        text = (ask or (lambda p: echo_business.ask_ai(p, timeout=120)))(prompt)
        m = re.search(r"\{.*\}", text or "", re.S)
        got = json.loads(m.group(0)) if m else {}
        if isinstance(got, dict):
            if isinstance(got.get("tagline"), str) and 3 < len(got["tagline"]) < 80:
                defaults["tagline"] = got["tagline"].strip()
            if isinstance(got.get("about"), str) and 20 < len(got["about"]) < 400:
                defaults["about"] = got["about"].strip()
            svc = [str(s).strip() for s in got.get("services", []) if 2 < len(str(s).strip()) < 40]
            if len(svc) >= 3:
                defaults["services"] = svc[:6]
    except Exception as exc:
        echo_log.error("sales copy", exc)
    return defaults


def _photo_data(lead):
    for p in lead.get("photos") or []:
        f = Path(p.get("file", ""))
        if f.is_file() and f.stat().st_size < 1_500_000:
            kind = "png" if f.suffix.lower() == ".png" else "jpeg"
            return f"data:image/{kind};base64," + base64.b64encode(f.read_bytes()).decode()
    return ""


def preview_html(lead, copy):
    e = lambda s: html.escape(str(s or ""), quote=True)
    accent, dark = _theme(lead.get("category", ""))
    phone = lead.get("phone") or ""
    tel = re.sub(r"[^\d+]", "", phone)
    photo = _photo_data(lead)
    hero_bg = (f"linear-gradient(rgba(0,0,0,.55),rgba(0,0,0,.55)),url('{photo}') center/cover" if photo
               else f"linear-gradient(135deg,{accent},{dark})")
    hours = "".join(f"<li>{e(h)}</li>" for h in lead.get("hours") or []) or "<li>Call us for opening hours</li>"
    services = "".join(f"<div class='card'><span>✓</span>{e(s)}</div>" for s in copy["services"])
    maps = lead.get("maps_url") or ""
    call = (f"<a class='btn' href='tel:{e(tel)}'>📞 Call {e(phone)}</a>" if tel
            else "<a class='btn' href='#contact'>Get in touch</a>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(lead['name'])}</title><style>
:root{{--a:{accent};--d:{dark}}}*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#1d2330;background:#f6f7f9}}
.demo{{background:#111;color:#fff;text-align:center;font-size:13px;padding:6px}}
header{{background:{hero_bg};color:#fff;padding:72px 20px 64px;text-align:center}}
h1{{font-size:clamp(30px,7vw,52px);margin:0 0 10px}}.tag{{font-size:clamp(17px,4vw,22px);opacity:.92;margin:0 0 26px}}
.btn{{display:inline-block;background:var(--a);color:#fff;text-decoration:none;padding:14px 26px;border-radius:999px;font-weight:700;font-size:17px;box-shadow:0 6px 20px rgba(0,0,0,.25)}}
section{{max-width:920px;margin:0 auto;padding:44px 20px}}h2{{color:var(--d);font-size:26px;margin:0 0 18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}}
.card{{background:#fff;border-radius:14px;padding:18px;box-shadow:0 2px 10px rgba(0,0,0,.06);font-weight:600}}.card span{{color:var(--a);margin-right:8px}}
.two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:24px}}ul{{padding-left:18px;line-height:1.8}}
.box{{background:#fff;border-radius:14px;padding:22px;box-shadow:0 2px 10px rgba(0,0,0,.06)}}a{{color:var(--a)}}
footer{{background:var(--d);color:#cfd6e4;text-align:center;padding:26px 20px;font-size:14px}}
</style></head><body>
<div class="demo">Free preview made for {e(lead['name'])}. Not live yet.</div>
<header><h1>{e(lead['name'])}</h1><p class="tag">{e(copy['tagline'])}</p>{call}</header>
<section><h2>What we do</h2><div class="grid">{services}</div></section>
<section><div class="two"><div class="box"><h2>About us</h2><p>{e(copy['about'])}</p></div>
<div class="box"><h2>Opening hours</h2><ul>{hours}</ul></div></div></section>
<section id="contact"><div class="box"><h2>Find us</h2><p>{e(lead.get('address') or 'Southern Adelaide, SA')}</p>
<p>{f"Phone: <a href='tel:{e(tel)}'>{e(phone)}</a><br>" if tel else ""}{f"<a href='{e(maps)}'>Open in Google Maps</a>" if maps else ""}</p></div></section>
<footer>© {date.today().year} {e(lead['name'])} · Website preview by Tailen</footer>
</body></html>"""


def build_preview(name, ask=None):
    """Make the preview website for a business. Returns (path, message)."""
    lead = find_lead(name)
    if not lead:
        return None, f"I can't find '{name}' in your leads. Send /leads to see them."
    copy = _copy(lead, ask)
    folder = Path(lead.get("folder") or "") if lead.get("folder") else None
    if not folder:
        import echo_leads
        folder = echo_leads.LEADS_DIR / "previews"
    folder.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", lead["name"].lower()).strip("-")[:40] or "business"
    path = folder / f"preview-{slug}.html"
    path.write_text(preview_html(lead, copy), encoding="utf-8")
    echo_business.record("Website and Leads Manager", "Built a preview site for " + lead["name"])
    return path, (f"🌐 Free preview website for {lead['name']} is ready (attached). Open it on your phone, "
                  "screenshot it, or send it to the owner. It's a mock-up: nothing is published.")


# ==========================================
# SELLING
# ==========================================

def price():
    return echo_business.load("sales_settings", {}).get("price", "")


def set_price(text):
    m = re.search(r"\$?\s?([\d,]+(?:\.\d{2})?)", text)
    if not m:
        return "Tell me like this: my website price is $499"
    s = echo_business.load("sales_settings", {})
    s["price"] = "$" + m.group(1)
    echo_business.save("sales_settings", s)
    return f"Got it: websites from {s['price']}. I'll put that in every pitch."


def sell(name, ask=None):
    """Pitch drafts + preview website. Returns (text, preview path or None)."""
    lead = find_lead(name)
    if not lead:
        return f"I can't find '{name}' in your leads. Send /leads to see them, or /findleads for new ones.", None
    pitch = echo_business.pitch(lead["name"])
    path, note = build_preview(lead["name"], ask)
    extra = f"\n\n💲 Your price: websites from {price()}." if price() else \
        "\n\nTip: set your price with 'my website price is $499' and I'll add it to pitches."
    return pitch + extra + "\n\n" + note, path


def scoreboard():
    p = echo_business._pipeline()
    if not p:
        return "📊 No businesses in the pipeline yet. Send /findleads to get some (free)."
    counts = {s: sum(l["stage"] == s for l in p.values()) for s in echo_business.STAGES}
    reached = sum(counts[s] for s in ("contacted", "follow up", "meeting", "won", "lost"))
    rate = f"{counts['won'] * 100 // reached}%" if reached else "n/a"
    lines = ["📊 Website sales scoreboard",
             f"🆕 New: {counts['new']} · 📨 Contacted: {counts['contacted'] + counts['follow up']} · "
             f"🤝 Meetings: {counts['meeting']}",
             f"✅ Said yes: {counts['won']} · ❌ Said no: {counts['lost']} · Win rate: {rate}"]
    won = [l["name"] for l in p.values() if l["stage"] == "won"]
    if won:
        lines.append("Customers: " + ", ".join(won[:8]))
    fu = echo_business.follow_ups()
    if fu.startswith("Follow-ups due"):
        lines.append("\n" + fu)
    best = sorted((l for l in p.values() if l["stage"] == "new"), key=lambda l: -len(l.get("reasons", [])))[:3]
    if best:
        lines.append("\nBest next ones to try: " + ", ".join(l["name"] for l in best) + " (say 'sell <name>')")
    return "\n".join(lines)


def morning_nudge():
    fu = echo_business.follow_ups()
    if not fu.startswith("Follow-ups due"):
        return ""
    return "📞 Sales reminder\n" + fu + "\n\nSay 'sell <name>' for a fresh message, or 'mark <name> won/lost'."


_SELL = re.compile(r"^/?(sell|preview)\s+(?:to\s+)?(?:a website to\s+)?(.{2,80}?)[.!?]*$", re.I)


def wants(text):
    """Quick check (no AI): is this message for the sales machine?"""
    t = (text or "").strip()
    m = _SELL.match(t)
    if m:
        return bool(find_lead(m.group(2))) or not re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", m.group(2))
    return bool(re.match(r"^(my )?(website )?price (is|=)\s*\$?\d|^my website price|^/sales\b|^(sales )?scoreboard\b|"
                         r"^how are (my )?sales", t, re.I))


def handle(text):
    """Telegram commands for selling websites. Returns (reply, file path or None), or None."""
    t = text.strip()
    m = re.match(r"^/?(sell|preview)\s+(?:to\s+)?(?:a website to\s+)?(.{2,80}?)[.!?]*$", t, re.I)
    if m:
        if not find_lead(m.group(2)) and re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", m.group(2)):
            return None  # "sell AAPL" is a trade, not a website sale
        if m.group(1).lower() == "sell":
            return sell(m.group(2))
        path, note = build_preview(m.group(2))
        return note, path
    if re.match(r"^(my )?(website )?price (is|=)\s*\$?\d", t, re.I) or re.match(r"^my website price", t, re.I):
        return set_price(t), None
    if re.match(r"^/sales\b|^(sales )?scoreboard\b|^how are (my )?sales", t, re.I):
        return scoreboard(), None
    return None
