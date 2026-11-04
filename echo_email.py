"""Echo's email: Sales and Support can send real emails from your Gmail, after your Yes.

Connect once with setup_echo.bat (see EMAIL_SETUP.md):
  gmail_address        you@gmail.com
  gmail_app_password   a 16-letter Google "app password" (not your normal password)

Every email is shown to you on Telegram first; it only goes out when you reply Yes.
"""
import json
import os
import re
import smtplib
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"
DIR = Path.home() / "Echo_business"
PENDING = DIR / "email_pending.json"
SENT_LOG = DIR / "emails_sent.json"
PENDING_MINUTES = 240

NOT_CONNECTED = ("I can't send emails yet: your Gmail isn't connected. Quickest fix: send /connect 3 and "
                 "I'll walk you through it from your phone (about 3 minutes).")


def _settings():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    addr = (os.getenv("ECHO_GMAIL") or str(data.get("gmail_address", ""))).strip()
    pw = (os.getenv("ECHO_GMAIL_APP_PASSWORD") or str(data.get("gmail_app_password", ""))).replace(" ", "")
    return addr, pw


def is_configured():
    a, p = _settings()
    return bool(a and p)


def _smtp():
    addr, pw = _settings()
    s = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30)
    try:
        s.login(addr, pw)
    except smtplib.SMTPAuthenticationError:
        s.close()
        raise RuntimeError("Gmail rejected the app password. Make a new one (EMAIL_SETUP.md) and run setup_echo.bat.") from None
    return s


def test():
    _smtp().quit()
    return "Gmail connected as " + _settings()[0] + "."


def send_now(to, subject, body):
    addr, _ = _settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = addr, to, subject
    msg.set_content(body)
    s = _smtp()
    try:
        s.send_message(msg)
    finally:
        s.quit()
    try:
        log = json.loads(SENT_LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = []
    log.append({"at": datetime.now().isoformat(timespec="seconds"), "to": to, "subject": subject})
    DIR.mkdir(parents=True, exist_ok=True)
    SENT_LOG.write_text(json.dumps(log[-500:], indent=2), encoding="utf-8")
    return f"✅ Email sent to {to}: \"{subject}\""


def propose(to, subject, body, who="Sales Agent", after=None):
    """Save a draft and ask Yes/No on Telegram. after = {'mark': lead name} to update the pipeline."""
    if not re.match(r"[^@\s]+@[^@\s]+\.[a-z]{2,}$", to or "", re.I):
        raise RuntimeError(f"'{to}' doesn't look like an email address.")
    DIR.mkdir(parents=True, exist_ok=True)
    plan = {"to": to, "subject": subject, "body": body, "who": who, "after": after or {},
            "created": datetime.now(timezone.utc).isoformat()}
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    msg = (f"✉️ {who} wants to email {to}\nSubject: {subject}\n\n{body}\n\nReply Yes to send it, or No to cancel.")
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
    return "OK, that email won't be sent."


def approve():
    plan = pending()
    if not plan:
        return "That email has expired or was already handled. Nothing was sent."
    PENDING.unlink(missing_ok=True)
    result = send_now(plan["to"], plan["subject"], plan["body"])
    try:
        import echo_business
        echo_business.record(plan.get("who", "Sales Agent"), "Emailed " + plan["to"])
        if plan.get("after", {}).get("mark"):
            echo_business.mark(plan["after"]["mark"], "contacted")
    except Exception:
        pass
    return result


def draft_for_lead(name):
    """Sales: write a real outreach email to a lead from the pipeline and ask to send it."""
    import echo_business
    if not is_configured():
        return NOT_CONNECTED
    p = echo_business._pipeline()
    _key, lead = echo_business._find(p, name)
    if not lead:
        return f"I can't find '{name}' in the pipeline. Say 'pipeline' to see the businesses."
    if not lead.get("email"):
        return f"{lead['name']} has no email address on file" + (f", but you can call them on {lead['phone']}." if lead.get("phone") else ".")
    facts = (f"Business: {lead['name']} ({lead['category']}), {lead['address']}. Website: {lead.get('website') or 'none'}. "
             f"Why they're a fit: {'; '.join(lead.get('reasons', []))}.")
    try:
        text = echo_business.ask_ai(
            "Write ONE short, friendly outreach email to this local Adelaide business offering a modern website. "
            "First line must be 'Subject: ...'. Under 120 words, no hype or fake claims, sign off as 'Tailen'.\n" + facts,
            timeout=180)
    except Exception:
        text = (f"Subject: A website for {lead['name']}\n\nHi there,\n\nI'm Tailen, a local web designer. I noticed "
                f"{lead['name']} doesn't have its own website yet. I build simple, affordable sites that help "
                "customers find and call you. Happy to send a free mock-up?\n\nCheers,\nTailen")
    m = re.match(r"\s*\**subject:?\**\s*(.+)", text, re.I)
    subject = m.group(1).strip() if m else "A website for " + lead["name"]
    body = text[m.end():].strip() if m else text.strip()
    msg, sent = propose(lead["email"], subject, body, "Sales Agent", {"mark": lead["name"]})
    return msg.rsplit("\n\n", 1)[0] + ("\n\n📱 Sent to your phone: tap ✅ Yes on Telegram to send it." if sent else
                                       "\n\nReply Yes on Telegram to send it.")


EMAIL_RE = re.compile(r"^\s*(?:/email\s+|(?:send\s+)?(?:an\s+)?email\s+(?:to\s+)?)(.+?)\s*$", re.I)


def handle(text):
    """'email Joe's Plumbing' (a lead), or 'email bob@x.com about ...'. Returns a reply or None."""
    m = EMAIL_RE.match(text)
    if not m:
        return None
    target = m.group(1)
    if not is_configured():
        return NOT_CONNECTED
    addr = re.search(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", target, re.I)
    try:
        if not addr:
            return draft_for_lead(target)
        about = target.replace(addr.group(0), "").strip(" ,:-") or "a quick hello"
        about = re.sub(r"^(about|saying|that)\s+", "", about, flags=re.I)
        import echo_business
        text = echo_business.ask_ai("Write a short, friendly email from Tailen about: " + about +
                                    "\nFirst line 'Subject: ...'. Under 120 words. Sign off as 'Tailen'.", timeout=180)
        mm = re.match(r"\s*\**subject:?\**\s*(.+)", text, re.I)
        subject = mm.group(1).strip() if mm else about[:60].capitalize()
        body = text[mm.end():].strip() if mm else text
        msg, sent = propose(addr.group(0), subject, body, "Communications Assistant")
        return msg.rsplit("\n\n", 1)[0] + ("\n\n📱 Sent to your phone for Yes/No." if sent else "\n\nReply Yes on Telegram to send it.")
    except RuntimeError as exc:
        return str(exc)
