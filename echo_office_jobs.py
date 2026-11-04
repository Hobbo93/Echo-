"""Daily jobs the offices do by themselves once their accounts are connected (/connect).

    Content Creator  7:30 AM   what's trending in Australia + 3 video ideas (hook, outline, caption) for your
                               channels, and long YouTube videos on your topic you could clip ('clip 2')
    Shopify Manager  8:45 AM   store report: latest orders and anything low on stock
    Customer Support every 15 min  new customer emails in Gmail become tickets, with a heads-up on Telegram
                               ('reply 3' drafts an answer, 'send reply 3' emails it after your Yes)

On demand: /ideas, /store, /inbox. Set your channels' topic with 'my channels are about funny animals'.
Reading Gmail never marks emails as read; newsletters and automatic emails are skipped.
Free: Google Trends, YouTube search and your local AI. Nothing is posted or sent without your Yes.
"""
import email
import email.policy
import email.utils
import imaplib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

import echo_business
import echo_log

SEEN = Path.home() / "Echo_business" / "inbox_seen.json"
SKIP_SENDERS = re.compile(r"no-?reply|notifications?@|mailer-daemon|newsletter|news@|marketing@|updates@|"
                          r"@(facebookmail|accounts\.google|youtube|tiktok|instagram|shopify|paypal)\.", re.I)


# ==========================================
# CONTENT CREATOR: morning ideas
# ==========================================

def niche():
    return echo_business.load("content_settings", {}).get("niche", "")


def set_niche(text):
    m = re.match(r"^\s*my (?:channels?|videos?|content|page) (?:is|are) about\s+(.+?)[.!]*$", text, re.I)
    if not m:
        return None
    s = echo_business.load("content_settings", {})
    s["niche"] = m.group(1).strip()[:120]
    echo_business.save("content_settings", s)
    return f"🎬 Got it: your channels are about {s['niche']}. Your 7:30 AM ideas will focus on that. /ideas for some now."


def trends_au(fetch=None):
    """Today's top Google searches in Australia (free RSS)."""
    try:
        if fetch:
            raw = fetch("https://trends.google.com/trending/rss?geo=AU")
        else:
            req = urllib.request.Request("https://trends.google.com/trending/rss?geo=AU",
                                         headers={"User-Agent": "Mozilla/5.0 (Echo)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read(2_000_000)
        return [i.findtext("title") for i in ET.fromstring(raw).iter("item") if i.findtext("title")][:10]
    except Exception as exc:
        echo_log.error("google trends", exc)
        return []


def _parse_ideas(text):
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        return []
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and str(it.get("title", "")).strip():
            out.append({k: " ".join(str(it.get(k, "")).split())[:300] for k in ("title", "hook", "outline", "caption")})
    return out[:3]


def content_ideas(ask=None, fetch=None, find=None):
    topic = niche() or "viral short clips"
    trends = trends_au(fetch)
    prompt = (f"You plan short videos (YouTube Shorts, TikTok, Instagram Reels) for an Australian creator whose "
              f"channels are about: {topic}.\nToday's top searches in Australia: {', '.join(trends) or 'unknown'}.\n"
              "Give 3 video ideas that fit the channels (use a trend only if it really fits). Original ideas only. "
              'Answer with ONLY JSON: [{"title": "...", "hook": "first 3 seconds, word for word", "outline": '
              '"3 quick beats", "caption": "caption with 3-5 hashtags"}]')
    try:
        ideas = _parse_ideas((ask or (lambda q: echo_business.ask_ai(q, timeout=240)))(prompt))
    except Exception as exc:
        echo_log.error("content ideas", exc)
        ideas = []
    lines = [f"🎬 Content Creator · {datetime.now():%a %d %b}", ""]
    if trends:
        lines.append("Trending in Australia today: " + ", ".join(trends[:8]))
    if ideas:
        lines.append("")
        for i, d in enumerate(ideas, 1):
            lines.append(f"{i}. {d['title']}\n   Hook: {d['hook']}\n   Plan: {d['outline']}\n   Caption: {d['caption']}")
    else:
        lines.append("\n(The AI brain was busy or off, so no ideas this time. /ideas to try again.)")
    try:
        import echo_finder
        found = (find or echo_finder.find)(f"find long videos about {topic}")
        lines += ["", found]
    except Exception as exc:
        echo_log.error("content finder", exc)
    if not niche():
        lines.append("\nTip: tell me what your channels are about, e.g. 'my channels are about funny animals'.")
    echo_business.record("Content Creator", "Sent today's video ideas")
    return "\n".join(lines)


# ==========================================
# SHOPIFY MANAGER: morning store report
# ==========================================

def store_report():
    import echo_shopify
    if not echo_shopify.is_configured():
        return ""
    parts = ["🛍️ Shopify Manager · morning store report"]
    for fn in (lambda: echo_shopify.orders(5), echo_shopify.low_stock):
        try:
            parts.append(fn())
        except Exception as exc:
            echo_log.error("store report", exc)
            parts.append(f"(Couldn't read the store: {str(exc)[:120]})")
    echo_business.record("Shopify Manager", "Sent the morning store report")
    return "\n\n".join(parts)


# ==========================================
# CUSTOMER SUPPORT: new emails become tickets
# ==========================================

def _seen():
    try:
        return set(json.loads(SEEN.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _save_seen(ids):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(ids)[-500:]), encoding="utf-8")


def _text(msg):
    part = msg.get_body(preferencelist=("plain", "html")) if hasattr(msg, "get_body") else None
    body = part.get_content() if part is not None else ""
    if part is not None and part.get_content_type() == "text/html":
        body = re.sub(r"<[^>]+>", " ", body)
    return " ".join(body.split())[:600]


def is_customer_email(msg):
    sender = msg.get("From", "")
    if SKIP_SENDERS.search(sender) or msg.get("List-Unsubscribe") or msg.get("List-Id"):
        return False
    if re.search(r"bulk|list|junk", msg.get("Precedence", ""), re.I) or msg.get("Auto-Submitted", "no") != "no":
        return False
    return True


def check_inbox(connect=None, notify=None, max_new=10):
    """Turn new customer emails into tickets. Returns how many were added."""
    import echo_email
    if not echo_email.is_configured():
        return 0
    addr, pw = echo_email._settings()
    box = connect() if connect else imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    added = 0
    try:
        if not connect:
            box.login(addr, pw)
        box.select("INBOX", readonly=True)  # read-only: nothing gets marked as read
        since = (datetime.now() - timedelta(days=2)).strftime("%d-%b-%Y")
        _typ, data = box.search(None, "UNSEEN", "SINCE", since)
        seen = _seen()
        for num in (data[0].split() if data and data[0] else [])[-max_new:]:
            _typ, parts = box.fetch(num, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), b"")
            msg = email.message_from_bytes(raw, policy=email.policy.default)
            mid = msg.get("Message-ID", "") or f"{msg.get('From')}|{msg.get('Date')}"
            if mid in seen:
                continue
            seen.add(mid)
            if not is_customer_email(msg):
                continue
            name, from_addr = email.utils.parseaddr(msg.get("From", ""))
            subject = str(make_header(decode_header(msg.get("Subject", "(no subject)"))))
            reply = echo_business.new_ticket(name or from_addr, f"{subject}: {_text(msg)}")
            tickets = echo_business.load("tickets", [])
            if tickets:
                tickets[-1].update(email=from_addr, subject=subject)
                echo_business.save("tickets", tickets)
            added += 1
            if notify:
                notify(f"📧 New email from {name or from_addr}: {subject}\n{_text(msg)[:300]}\n\n{reply}")
        _save_seen(seen)
    finally:
        try:
            box.logout()
        except Exception:
            pass
    return added


def send_reply(num):
    """'send reply 3': email the drafted answer to that customer, after a Yes."""
    import echo_email
    tickets = echo_business.load("tickets", [])
    tk = next((t for t in tickets if t["no"] == num), None)
    if not tk:
        return f"No ticket #{num}."
    if not tk.get("email"):
        return f"Ticket #{num} didn't come from email, so I don't have an address to reply to."
    if not echo_email.is_configured():
        return echo_email.NOT_CONNECTED
    draft = echo_business.draft_reply(num)
    body = draft.split("\n\n", 1)[1].rsplit("\n\nYou send it.", 1)[0] if "\n\n" in draft else draft
    msg, sent = echo_email.propose(tk["email"], "Re: " + tk.get("subject", "your message"), body, "Customer Support")
    return "📱 Sent to your phone: tap Yes to email it." if sent else msg


def handle(text):
    t = text.strip()
    low = t.lower()
    reply = set_niche(t)
    if reply:
        return reply
    m = re.match(r"^send reply\s+#?(\d+)", low)
    if m:
        return send_reply(int(m.group(1)))
    return None
