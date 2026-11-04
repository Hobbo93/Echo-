"""Echo does simple things on your PC when you ask on Telegram (free, no AI needed).

    "search youtube for dog grooming tips"   opens the YouTube search on the PC
    "google cheap dog beds"                   opens a Google search
    "open my shopify admin" / "open gmail"   opens the site
    "open https://example.com"               opens the link
    /screen or "show me my screen"           sends you a picture of the PC screen

After opening something, Echo waits a few seconds and sends you a screenshot so you can
see what's on the screen. It only opens web pages: it never runs programs, types, clicks,
or enters passwords. Standard library only; screenshots come from echo_photos.screenshot().
"""
import json
import os
import re
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"
SHOT_WAIT_SECONDS = 5

SEARCH = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "maps": "https://www.google.com/maps/search/{q}",
    "images": "https://www.google.com/search?tbm=isch&q={q}",
    "amazon": "https://www.amazon.com.au/s?k={q}",
    "ebay": "https://www.ebay.com.au/sch/i.html?_nkw={q}",
    "tiktok": "https://www.tiktok.com/search?q={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={q}",
}
SEARCH_ALIASES = {"yt": "youtube", "google maps": "maps", "google images": "images", "the web": "google",
                  "online": "google", "the internet": "google", "wiki": "wikipedia"}


def _shopify_admin():
    try:
        store = json.loads(CONFIG.read_text(encoding="utf-8-sig")).get("shopify_store", "")
    except (OSError, ValueError, AttributeError):
        store = ""
    store = store or "thedogden-2.myshopify.com"
    return f"https://{store.replace('https://', '').strip('/')}/admin"


SITES = {
    "youtube studio": "https://studio.youtube.com", "youtube": "https://www.youtube.com",
    "shopify admin": _shopify_admin, "shopify": _shopify_admin, "my store": _shopify_admin,
    "shopify dev dashboard": "https://dev.shopify.com/dashboard", "dev dashboard": "https://dev.shopify.com/dashboard",
    "opusclip": "https://clip.opus.pro/dashboard", "opus clip": "https://clip.opus.pro/dashboard",
    "gmail": "https://mail.google.com", "email": "https://mail.google.com",
    "instagram": "https://www.instagram.com", "tiktok": "https://www.tiktok.com",
    "facebook": "https://www.facebook.com", "google": "https://www.google.com",
    "github": "https://github.com/Hobbo93/Echo-", "echo hq": "http://127.0.0.1:5000",
    "the office": "http://127.0.0.1:5000", "base44": "https://app.base44.com",
    "anthropic console": "https://console.anthropic.com", "alpaca": "https://app.alpaca.markets",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
}

_SEARCH_RE = re.compile(
    r"^(?:hey echo,?\s*|echo,?\s*)?(?:can you |could you |please |pls )?(?:go on |go to |on )?"
    r"(?:search|look up|look for|find|google)\s+(?:on\s+)?(?:(?P<site1>youtube|yt|google maps|google images|google|maps|"
    r"amazon|ebay|tiktok|reddit|wikipedia|wiki|the web|the internet|online)\s+(?:for\s+)?)?(?P<q>.+?)"
    r"(?:\s+on\s+(?P<site2>youtube|yt|google maps|google images|google|maps|amazon|ebay|tiktok|reddit|wikipedia))?(?: for me)?[.!?]*$", re.I)
_GO_SEARCH_RE = re.compile(
    r"^(?:hey echo,?\s*|echo,?\s*)?(?:can you |could you |please )?(?:go on|go to|open)\s+(?P<site>youtube|google|amazon|ebay|"
    r"tiktok|reddit)\s+(?:and\s+)?(?:search|look up|find)\s+(?:for\s+)?(?P<q>.+?)[.!?]*$", re.I)
_OPEN_RE = re.compile(r"^(?:hey echo,?\s*|echo,?\s*)?(?:can you |could you |please |pls )?(?:open|go to|pull up|bring up|load)"
                      r"\s+(?:up\s+)?(?:my\s+|the\s+)?(?P<what>.+?)(?:\s+on (?:my|the) (?:pc|computer))?(?: for me)?[.!?]*$", re.I)
_SCREEN_RE = re.compile(r"^/screen\b|\b(show me|send me|what'?s on|whats on|screenshot)\b.*\b(my |the )?(screen|pc|computer|desktop)\b|"
                        r"^screenshot[.!?]*$", re.I)


def search_url(site, query):
    site = SEARCH_ALIASES.get(site.lower(), site.lower()) if site else "google"
    return SEARCH.get(site, SEARCH["google"]).format(q=urllib.parse.quote_plus(query.strip()))


def plan(text):
    """What a message asks the PC to do: {'action': 'open'|'screen', 'url', 'label'} or None."""
    t = (text or "").strip()
    if _SCREEN_RE.search(t):
        return {"action": "screen", "label": "your screen"}
    m = _GO_SEARCH_RE.match(t)
    if m:
        return {"action": "open", "url": search_url(m.group("site"), m.group("q")),
                "label": f"{m.group('site').title()} search for \"{m.group('q')}\""}
    m = _SEARCH_RE.match(t)
    if m and (m.group("site1") or m.group("site2") or re.match(r"^(?:\w+\s+)*google\b", t, re.I)):
        site = m.group("site1") or m.group("site2") or "google"
        site = SEARCH_ALIASES.get(site.lower(), site.lower())
        return {"action": "open", "url": search_url(site, m.group("q")),
                "label": f"{site.title()} search for \"{m.group('q')}\""}
    m = _OPEN_RE.match(t)
    if m:
        what = m.group("what").strip().lower()
        url = re.match(r"https?://\S+$", m.group("what").strip())
        if url:
            return {"action": "open", "url": url.group(0), "label": url.group(0)}
        for name in sorted(SITES, key=len, reverse=True):  # longest name first ("youtube studio" before "youtube")
            if what == name or what == name + " website" or what == name + " page":
                target = SITES[name]
                return {"action": "open", "url": target() if callable(target) else target, "label": name.title()}
    return None


def open_url(url):
    if not re.match(r"https?://", url):
        raise ValueError("I only open web links (http or https).")
    if not webbrowser.open(url, new=2):
        raise RuntimeError("Couldn't open the web browser on the PC.")


def screenshot():
    """Picture of the whole PC screen (all monitors). Returns the file path."""
    import echo_photos
    return str(echo_photos.screenshot())


def do(p, wait=SHOT_WAIT_SECONDS):
    """Carry out a plan. Returns (message, screenshot path or None). Never raises."""
    shot_err = ""
    try:
        if p["action"] == "open":
            open_url(p["url"])
            time.sleep(wait)
            msg = f"✅ Opened {p['label']} on your PC."
        else:
            msg = "🖥️ Here's your screen right now."
    except Exception as exc:
        return f"❌ Couldn't do that on the PC: {exc}", None
    try:
        path = screenshot()
    except Exception as exc:
        path, shot_err = None, f" (No screenshot: {exc})"
    return msg + shot_err, path


if __name__ == "__main__":  # quick manual test: py echo_computer.py "search youtube for dog tricks"
    text = " ".join(sys.argv[1:]) or "/screen"
    p = plan(text)
    print(p or "Not a PC request.")
    if p and os.name == "nt":
        print(do(p))
