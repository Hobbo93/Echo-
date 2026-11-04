"""What every Echo office is connected to, and what it still needs.

/connections on Telegram, or GET /api/connections. Each office says honestly
whether it can do real work, and the exact step to connect it.
"""
import json
import urllib.request
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"


def _cfg():
    try:
        d = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _ollama():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3):
            return True
    except OSError:
        return False


def check_all(live=False):
    """List of {office, service, ok, does, how}. live=True also tests each login."""
    c = _cfg()
    out = []

    def add(office, service, ok, does, how, test=None):
        detail = ""
        if ok and live and test:
            try:
                detail = test()
            except Exception as exc:
                ok, detail = False, str(exc)[:200]
        out.append({"office": office, "service": service, "ok": bool(ok), "does": does,
                    "how": "" if ok else how, "detail": detail})

    import echo_shopify, echo_email, echo_broker, echo_trading
    add("Echo's brain (all offices)", "Ollama on this PC", _ollama(), "Thinks, writes and answers",
        "Open the Ollama app on the PC.")
    import echo_telegram
    add("Telegram (approvals + chat)", "Telegram bots", echo_telegram.is_configured(),
        "Texts you, sends photos, takes your Yes/No", "Run setup_echo.bat (TELEGRAM_SETUP.md).")
    add("Shopify Manager", "Your Shopify store", echo_shopify.is_configured(),
        "Adds products, changes prices and stock, discount codes, reads orders",
        "SHOPIFY_SETUP.md, then connect_echo.bat (store address + Client ID + Client secret).",
        echo_shopify.test)
    venue = echo_trading.settings()["venue"]
    add("Day Trading Desk", "Alpaca broker", echo_broker.is_configured(),
        f"Buys and sells for you after your Yes ({echo_broker.mode()}); venue now: {venue}",
        "TRADING_SETUP.md, then connect_echo.bat (Alpaca key ID + secret). Until then it uses a practice account.",
        lambda: "Equity $" + format(echo_broker.account()["equity"], ",.2f"))
    add("Sales Agent + Support", "Your Gmail", echo_email.is_configured(),
        "Sends outreach and replies from your Gmail after your Yes",
        "EMAIL_SETUP.md, then connect_echo.bat (Gmail address + app password).", echo_email.test)
    add("Website and Leads Manager", "Google Places", c.get("google_places_key"),
        "Finds 20 local businesses a day with phone, email and photos",
        "LEADS_SETUP.md, then connect_echo.bat (Google Places key).")
    add("Phone line", "Twilio", c.get("twilio_account_sid") and c.get("twilio_auth_token"),
        "Rings you for approvals and briefings", "PHONE_SETUP.md, then connect_echo.bat (say y to phone calls).")
    try:
        import echo_photos
        vision = echo_photos.has_vision()
    except Exception:
        vision = False
    add("Photos", "Vision model", vision, "Understands photos you send", "Send /getvision on Telegram.")
    import echo_opusclip
    add("Content Creator + Video Editor", "OpusClip", echo_opusclip.is_configured(),
        "Makes short clips and posts them to YouTube, Instagram and TikTok after your Yes",
        "OPUSCLIP_SETUP.md, then connect_echo.bat (OpusClip API key from the dashboard, bottom left).",
        echo_opusclip.test)
    add("Web Designer", "Base44", False, "Builds the websites for leads",
        "Base44 has no API Echo can use from the PC, so Echo prepares each lead's folder and "
        "Claude builds the site in Base44 with your connection.")
    return out


def summary(live=True):
    rows = check_all(live)
    good = [r for r in rows if r["ok"]]
    lines = [f"🔌 CONNECTIONS: {len(good)} of {len(rows)} ready", ""]
    for r in rows:
        lines.append(("🟢 " if r["ok"] else "🔴 ") + r["office"] + " → " + r["service"])
        lines.append("    " + (r["detail"] or r["does"]) if r["ok"] else "    Needs: " + r["how"])
    lines += ["", "To connect anything: double-click connect_echo.bat on the PC; it walks you through each one."]
    return "\n".join(lines)


def needs(office_keyword):
    """What one office is missing (for the HQ panels), or ''."""
    for r in check_all():
        if office_keyword.lower() in r["office"].lower() and not r["ok"]:
            return "Not connected to " + r["service"] + " yet: " + r["how"]
    return ""


if __name__ == "__main__":
    print(summary())
