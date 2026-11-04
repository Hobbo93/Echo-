"""Sends what you say on Telegram to the part of Echo that can really do it.

Two problems this fixes:
1. "Are you connected to Shopify?" used to be answered by the chat model, which guessed (and
   said yes). Now connection questions are answered from a real live check of each service.
2. "Post clip 2 to YouTube" or "change the dog bed price to $49" used to reach the chat model,
   which can't do anything. Now plain-English requests go to the same tools as the commands
   (/post, /clip, the Shopify Manager, email), which ask for your Yes before acting.

route(text) returns (kind, value) or None:
    ("connections", reply)      already answered from the live checks
    ("opus", "/post 2 youtube") an OpusClip command to run
    ("shopify", text)           a store request for the Shopify Manager
    ("email", "/email ...")     an email request
Standard library only.
"""
import re

SERVICES = [  # (words you might use, service name in echo_connections, what to try once connected)
    (r"shopify|store|shop|furventure|products?", "Your Shopify store",
     "\"show my products\", \"change Dog Bed price to $49\", \"add a dog jacket to my store, $39.95, 20 in stock\""),
    (r"opus ?clip|opus|youtube|yt|instagram|insta|ig|tiktok|clips?|shorts|reels|socials?|social media", "OpusClip",
     "\"clip this https://youtube.com/...\", \"post clip 1 to youtube and instagram at 6pm\""),
    (r"g ?mail|e-?mails?", "Your Gmail", "\"email bob@example.com about the website quote\""),
    (r"alpaca|broker|trad(e|es|ing)|stocks?|shares", "Alpaca broker", "\"/trade propose\""),
    (r"twilio|phone|calls?|ring", "Twilio", "\"/callme\""),
    (r"google places|places|leads?", "Lead finder", "\"/leads\""),
    (r"telegram", "Telegram bots", ""),
    (r"ollama|brain|ai model|model", "Ollama on this PC", ""),
    (r"base44|websites?", "Base44", ""),
    (r"vision|photos?|pictures?|images?", "Vision model", "send me a photo"),
]
_QUESTION_START = re.compile(r"^\s*(are|is|r|can|could|do|does|have|has|did|what'?s|what is|which|check|tell me if|"
                             r"how many|what are)\b", re.I)
_CONNECT_WORDS = re.compile(r"\b(connected|connection|connections|linked|hooked up|set ?up|plugged in|access|"
                            r"logged in|integrated|working)\b|\bcan (you|u|echo) (use|see|reach|post|control|get into)\b", re.I)

_URL = re.compile(r"https?://\S+")
_PLATFORM = re.compile(r"\b(youtube|yt|shorts|instagram|insta|ig|reels|tiktok|facebook|fb|linkedin|twitter|x|all|everywhere)\b", re.I)
_WHEN = re.compile(r"\b(tomorrow\s+)?(at \d{1,2}(:\d{2})?\s*(am|pm)?|in \d{1,2} ?(hours?|hrs?|minutes?|mins?))\b", re.I)
_DO = r"(post|upload|publish|schedule|share|put|send)"
_STORE_DO = re.compile(r"\b(add|change|set|update|put|make|create|edit|remove|delete|archive|publish|unpublish|"
                       r"list|show|lower|raise|drop|increase|decrease|restock)\b", re.I)
_STORE_THING = re.compile(r"\b(price|prices|stock|inventory|discount|coupon|code|product|products|listing|listings|"
                          r"orders?|sale)\b", re.I)


def is_connection_question(text):
    t = (text or "").strip()
    if t.lower().startswith("/connections"):
        return True
    return bool(_CONNECT_WORDS.search(t) and (t.endswith("?") or _QUESTION_START.match(t)))


def _mentioned(text):
    low = text.lower()
    return [(name, tip) for words, name, tip in SERVICES if re.search(r"\b(" + words + r")\b", low)]


def answer_connections(text, live=True):
    """Honest status from real checks (live=True actually logs in to each service)."""
    import echo_connections
    rows = echo_connections.check_all(live=live)
    wanted = _mentioned(text)
    tips = {name: tip for name, tip in wanted}
    if wanted:
        rows = [r for r in rows if r["service"] in tips] or rows
    lines = []
    for r in rows:
        if r["ok"]:
            line = f"🟢 {r['office']} → {r['service']}: connected and working."
            if r["detail"]:
                line += f" ({r['detail']})"
            if tips.get(r["service"]):
                line += f"\n    Try: {tips[r['service']]}"
        else:
            reason = f" Check failed: {r['detail']}." if r["detail"] else ""
            line = (f"🔴 {r['office']} → {r['service']}: NOT connected, so I can't do anything there yet.{reason}"
                    f"\n    To fix: {r['how'] or 'run connect_echo.bat on the PC.'}")
        lines.append(line)
    head = "Here's what I checked just now (a real test, not a guess):\n\n"
    tail = ("\n\nKeys are only ever typed into connect_echo.bat on the PC, never into chat."
            if any(not r["ok"] for r in rows) else "")
    return head + "\n".join(lines) + tail


def opus_command(text):
    """Plain English → an OpusClip command, or None."""
    t = text.strip()
    low = t.lower()
    url = _URL.search(t)
    if url and re.search(r"\b(clip|clips|cut|shorts|reels|opus|opusclip)\b", low):
        return "/clip " + url.group(0)
    if re.search(r"\bclips?\b.*\b(latest|newest|last)\b.*\bvideo\b|\b(latest|newest|last) video\b.*\bclips?\b", low):
        return "/clip latest"
    m = (re.search(_DO + r"\b.*?\bclip\s*(?:number\s*|no\.?\s*)?#?(\d{1,2})\b", low)
         or re.search(_DO + r"\b.*?\b(\d{1,2})(?:st|nd|rd|th)? clip\b", low)
         or re.search(r"\bclip\s*#?(\d{1,2})\b.*\b" + _DO + r"\b", low))
    if m:
        n = next(g for g in m.groups() if g and g.isdigit())
        platforms = " ".join(dict.fromkeys(p.lower() for p in _PLATFORM.findall(low)))
        when = _WHEN.search(low)
        return f"/post {n} {platforms} {when.group(0) if when else ''}".strip()
    if re.search(r"\b(show|list|see|send|what are)\b.*\b(my |the )?clips\b|^my clips\b", low):
        return "/clips"
    if re.search(r"\bwhere can you post\b|\bwhich (social )?accounts\b", low):
        return "/opus"
    return None


def email_command(text):
    """'send Joe an email about X' / 'can you email bob@x.com ...' → '/email ...', or None."""
    t = text.strip()
    m = re.match(r"^(?:can you |could you |please |pls )?(?:send|write|draft)\s+(.+?)\s+an?\s+e-?mail"
                 r"(?:\s+(?:about|saying|that)\s+(.+))?[.?!]*$", t, re.I)
    if m:
        return "/email " + m.group(1) + (" about " + m.group(2) if m.group(2) else "")
    m = re.match(r"^(?:can you |could you |please |pls )(?:e-?mail)\s+(.+?)[.?!]*$", t, re.I)
    if m:
        return "/email " + m.group(1)
    return None


def is_store_request(text):
    low = (text or "").lower()
    if re.search(r"\b(shopify|my store|the store|furventure|my shop)\b", low):
        return True
    return bool(_STORE_DO.search(low) and _STORE_THING.search(low) and not _URL.search(low)
                and not re.search(r"\b(clip|video|trade|trading|shares?|crypto|bitcoin|stock market|market|asx|nasdaq|ticker|"
                          r"nvda|tsla|aapl|amzn|msft|spy|qqq|roblox|map|game)\b", low))


def route(text):
    if not text or text.startswith("/") and not text.lower().startswith("/connections"):
        return None
    if is_connection_question(text):
        return "connections", None
    cmd = opus_command(text)
    if cmd:
        return "opus", cmd
    cmd = email_command(text)
    if cmd:
        return "email", cmd
    if is_store_request(text):
        return "shopify", text
    return None


# Added to every chat prompt, so when the chat model is asked to DO something it points to
# the real way instead of pretending.
COMMANDS_HELP = (
    "If the owner asks you to DO something, you can't do it from this chat reply. Don't pretend. Tell them the "
    "exact way that works (they can also just say it in plain English and Echo routes it):\n"
    "- Clips: \"clip this <link>\" or /clip latest; post: \"post clip 1 to youtube and instagram at 6pm\"\n"
    "- Shopify: \"show my products\", \"change Dog Bed price to $49\", \"add a dog jacket to my store, $39.95\"\n"
    "- Email: \"email bob@example.com about ...\" · Trading: /trade propose · Research: /research add TOPIC\n"
    "- Is something connected? \"are you connected to shopify?\" runs a real check.\n"    "- On the PC: \"search youtube for ...\", \"google ...\", \"open my shopify admin\", /screen for a screenshot. "
    "Echo can open pages and show the screen, but can't click, type or take over the computer.\n"
    "- Trading: \"stop trading\" pauses everything at once, \"sell everything\" sells all (asks Yes), "
    "\"resume trading\" turns it back on.\n"
    "- Step-by-step help on the PC: \"/guide connect my shopify store\" (Echo looks at the screen and says where to click).\n"
    "Only say a service is connected if it's in the connected list above."
)
