"""Find videos and send them to OpusClip to be cut into clips.

    find videos about funny dog fails        Echo searches YouTube (free, no key) and sends the top 5
    find long videos about AFL highlights    only videos over 5 minutes (best for OpusClip)
    clip 2                                   send video 2 to OpusClip (asks your Yes first)
    open 2                                   play video 2 on the PC
    <paste a link>                           a YouTube, TikTok, Instagram or Facebook link: Echo keeps it
    clip it                                  send the link you just pasted to OpusClip

Instagram, TikTok and Facebook don't allow searching without logging in, so for those: in the app
tap Share → Copy link, and paste it to Echo. OpusClip does the editing; Echo never posts anything
without your Yes. Only clip videos you own or have permission to use: reposting other people's
videos can get your channels struck down.
"""
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

import echo_log

STATE = Path.home() / "Echo_business" / "found_videos.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
LINK = re.compile(r"https?://(?:www\.|m\.|vm\.|vt\.)?(?:youtube\.com|youtu\.be|tiktok\.com|instagram\.com|"
                  r"facebook\.com|fb\.watch|x\.com|twitter\.com|twitch\.tv|vimeo\.com)/\S+", re.I)
RIGHTS = "Only clip videos you own or have permission to use. Reposting other people's videos can get your channels struck."

_FIND = re.compile(r"^(?:hey echo,?\s*)?(?:can you |please |pls )?(?:/find\s+|(?:find|search|get|look for)\s+(?:me\s+)?"
                   r"(?:some\s+|a few\s+)?(?P<long>long\s+)?(?:youtube\s+)?videos?\s+(?:about|of|on|for)\s+|"
                   r"search youtube for\s+|find\s+(?P<q2>.+?)\s+on youtube$)(?P<q>.*?)(?:\s+on youtube)?[.!?]*$", re.I)


def _load():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def _seconds(length):
    try:
        parts = [int(x) for x in (length or "").split(":")]
    except ValueError:
        return 0
    total = 0
    for p in parts:
        total = total * 60 + p
    return total


def _videos(data):
    out = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if isinstance(v, dict) and v.get("videoId"):
                runs = lambda k: ((v.get(k) or {}).get("runs") or [{}])[0].get("text", "")
                out.append({"id": v["videoId"], "title": runs("title"), "channel": runs("ownerText"),
                            "length": (v.get("lengthText") or {}).get("simpleText", ""),
                            "views": (v.get("viewCountText") or {}).get("simpleText", ""),
                            "ago": (v.get("publishedTimeText") or {}).get("simpleText", ""),
                            "url": "https://www.youtube.com/watch?v=" + v["videoId"]})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(data)
    return out


def search_youtube(query, n=5, long_only=False, fetch=None):
    """Top YouTube videos for a search (free, no key). Raises RuntimeError if YouTube can't be read."""
    url = ("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query) +
           "&sp=EgIQAQ%253D%253D")  # videos only
    if fetch:
        page = fetch(url)
    else:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read(5_000_000).decode("utf-8", "ignore")
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", page, re.S)
    if not m:
        raise RuntimeError("YouTube changed its page, so I couldn't read the results. Tell Claude so it can fix it.")
    vids = [v for v in _videos(json.loads(m.group(1))) if v["length"]]  # skip live streams
    if long_only:
        vids = [v for v in vids if _seconds(v["length"]) >= 300]
    return vids[:n]


def find(text, fetch=None):
    m = _FIND.match(text.strip())
    query = (m.group("q") or m.group("q2") or "").strip() if m else text.strip()
    if len(query) < 2:
        return "What should I look for? e.g. 'find videos about funny dog fails'"
    long_only = bool(m and m.group("long"))
    try:
        vids = search_youtube(query, 5, long_only, fetch)
    except Exception as exc:
        echo_log.error("youtube search", exc)
        return f"I couldn't search YouTube right now ({str(exc)[:120]})."
    if not vids:
        return f"No YouTube videos found for '{query}'."
    s = _load()
    s.update(found=vids, query=query, at=time.time())
    _save(s)
    lines = [f"🔎 Top YouTube videos for '{query}':"]
    for i, v in enumerate(vids, 1):
        lines.append(f"\n{i}. {v['title']}\n   {v['channel']} · {v['length']} · {v['views']} · {v['ago']}\n   {v['url']}")
    lines.append("\nSay 'clip 2' to send one to OpusClip, or 'open 2' to watch it on the PC.\n⚠️ " + RIGHTS)
    return "\n".join(lines)


def pick(n):
    found = _load().get("found", [])
    if not 1 <= n <= len(found):
        return None
    return found[n - 1]


def remember_link(url):
    s = _load()
    s["link"] = url
    s["link_at"] = time.time()
    _save(s)
    raw = re.search(r"//(?:www\.|m\.|vm\.|vt\.)?([a-z]+)", url, re.I).group(1).lower()
    site = {"youtube": "YouTube", "youtu": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook",
            "fb": "Facebook", "x": "X", "twitter": "X", "twitch": "Twitch", "vimeo": "Vimeo"}.get(raw, raw.title())
    return (f"📎 Got your {site} link. Say 'clip it' to send it to OpusClip for editing "
            "(I'll ask your Yes first), or 'open it' to watch it on the PC.")


def last_link(max_age=6 * 3600):
    s = _load()
    if s.get("link") and time.time() - s.get("link_at", 0) < max_age:
        return s["link"]
    return None


def clip(url):
    """Hand a video link to OpusClip through Echo's normal Yes/No flow."""
    import echo_opusclip
    return echo_opusclip.handle("/clip " + url)


WANTS = re.compile(r"^/find\b|^(?:hey echo,?\s*)?(?:can you |please |pls )?(?:find|search|get|look for)\s+(?:me\s+)?"
                   r"(?:some\s+|a few\s+)?(?:long\s+)?(?:youtube\s+)?videos?\s+(?:about|of|on|for)\s|^search youtube for\s|"
                   r"^find\s+.+\s+on youtube[.!?]*$|^(?:clip|open|send)\s+(?:video\s+)?#?\d\b|^(?:clip|open) (?:it|that)\b|"
                   r"^send (?:it|that) to opus", re.I)


def wants(text):
    t = (text or "").strip()
    if LINK.fullmatch(t) or (LINK.search(t) and len(t.split()) <= 3 and not re.search(r"\bclip\b", t, re.I)):
        return True
    return bool(WANTS.match(t))


def handle(text, fetch=None):
    """Returns a reply, or None if the message isn't for the video finder."""
    t = text.strip()
    link = LINK.search(t)
    if link and (LINK.fullmatch(t) or len(t.split()) <= 3) and not re.search(r"\bclip\b", t, re.I):
        return remember_link(link.group(0))
    m = re.match(r"^(clip|send|open)\s+(?:video\s+)?#?(\d)\b", t, re.I)
    if m:
        v = pick(int(m.group(2)))
        if not v:
            return "I don't have a video with that number. Say 'find videos about ...' first."
        if m.group(1).lower() == "open":
            return ("open", v["url"])
        return clip(v["url"])
    if re.match(r"^(clip it|clip that|send (it|that) to opus)", t, re.I):
        url = last_link()
        return clip(url) if url else "Paste a video link first, then say 'clip it'."
    if re.match(r"^open (it|that)\b", t, re.I):
        url = last_link()
        return ("open", url) if url else "Paste a video link first."
    if WANTS.match(t):
        return find(t, fetch)
    return None
