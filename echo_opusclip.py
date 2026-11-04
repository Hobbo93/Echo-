"""Echo's OpusClip connection: long videos in, short clips out, posted after your Yes.

    /clip https://youtube.com/watch?v=...   clip a video from a link
    /clip latest                            clip the newest video in the content_input folder
    /clips                                  your latest clips (numbered) and projects in progress
    /post 2 youtube instagram               post clip 2 now
    /post 2 tiktok at 6pm                   schedule it (Adelaide time)
    /opus                                   which social accounts OpusClip can post to

Making clips uses OpusClip credits and posting is public, so both are sent to your phone
first and only happen when you reply Yes. Echo checks running projects every few minutes
and messages you when the clips are ready.

Connect once: OpusClip dashboard > API key (bottom left), then connect_echo.bat
(saved as opusclip_api_key in %USERPROFILE%\\.echo_telegram.json). Standard library only.
API docs: https://help.opus.pro/api-reference/overview
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.opus.pro/api"
CONFIG = Path.home() / ".echo_telegram.json"
DIR = Path.home() / "Echo_business"
PENDING = DIR / "opusclip_pending.json"
STATE = DIR / "opusclip_projects.json"
LOG = DIR / "opusclip_log.json"
INPUT = Path(__file__).with_name("content_input")
TZ = ZoneInfo("Australia/Adelaide")
PENDING_MINUTES = 120
VIDEO_TYPES = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}

PLATFORMS = {"youtube": "YOUTUBE", "yt": "YOUTUBE", "shorts": "YOUTUBE", "instagram": "INSTAGRAM_BUSINESS",
             "insta": "INSTAGRAM_BUSINESS", "ig": "INSTAGRAM_BUSINESS", "reels": "INSTAGRAM_BUSINESS",
             "tiktok": "TIKTOK_BUSINESS", "facebook": "FACEBOOK_PAGE", "fb": "FACEBOOK_PAGE",
             "linkedin": "LINKEDIN", "twitter": "TWITTER", "x": "TWITTER"}
NICE = {"YOUTUBE": "YouTube", "INSTAGRAM_BUSINESS": "Instagram", "TIKTOK_BUSINESS": "TikTok",
        "FACEBOOK_PAGE": "Facebook", "LINKEDIN": "LinkedIn", "TWITTER": "X"}

NOT_CONNECTED = ("I'm not connected to OpusClip yet, so I can't make or post clips. One-time setup: in the "
                 "OpusClip dashboard copy your API key (bottom-left corner), then double-click "
                 "connect_echo.bat on the PC and paste it in. Never send the key in chat.")


class OpusError(RuntimeError):
    pass


# ==========================================
# CONNECTION
# ==========================================

def _settings():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    return {"key": (os.getenv("OPUSCLIP_API_KEY") or str(data.get("opusclip_api_key", ""))).strip(),
            "org": (os.getenv("OPUSCLIP_ORG_ID") or str(data.get("opusclip_org_id", ""))).strip()}


def is_configured():
    return bool(_settings()["key"])


def _api(method, path, body=None, query=None):
    s = _settings()
    if not s["key"]:
        raise OpusError(NOT_CONNECTED)
    url = API + path + ("?" + urllib.parse.urlencode(query) if query else "")
    headers = {"Authorization": "Bearer " + s["key"], "Accept": "application/json"}
    if s["org"]:
        headers["x-opus-org-id"] = s["org"]
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            raise OpusError("OpusClip rejected the API key. Paste a fresh one with connect_echo.bat.") from None
        if exc.code == 403 and "MONTHLY_CAP" in detail:
            raise OpusError("OpusClip's monthly API limit is used up. It resets on the 1st of next month "
                            "(the OpusClip website still works).") from None
        if exc.code == 429:
            raise OpusError("OpusClip says too many requests. Try again in a minute.") from None
        raise OpusError(f"OpusClip error {exc.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise OpusError(f"Couldn't reach OpusClip ({exc}). Check the internet connection.") from None
    return json.loads(raw) if raw.strip() else {}


def accounts():
    """Social accounts linked in OpusClip: [{postAccountId, subAccountId, platform, extUserName}]."""
    return _api("GET", "/social-accounts", query={"q": "mine"}).get("data", [])


def test():
    acc = accounts()
    names = ", ".join(f"{NICE.get(a['platform'], a['platform'])} ({a.get('extUserName', '?')})" for a in acc)
    return f"Can post to: {names}" if acc else "Connected, but no social accounts are linked in OpusClip yet."


def describe_accounts():
    if not is_configured():
        return NOT_CONNECTED
    return "🎬 OpusClip is connected. " + test()


# ==========================================
# PROJECTS AND CLIPS
# ==========================================

def _load_state():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
        s = s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        s = {}
    s.setdefault("projects", [])
    s.setdefault("last_clips", [])
    return s


def _save_state(s):
    DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


def latest_video():
    files = [f for f in INPUT.glob("*") if f.suffix.lower() in VIDEO_TYPES] if INPUT.exists() else []
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def upload(path):
    """Upload a local video to OpusClip's storage. Returns the uploadId to use as videoUrl."""
    link = _api("POST", "/upload-links", {"video": {"usecase": "LocalUpload"}})
    start = urllib.request.Request(link["url"], data=b"", method="POST",
                                   headers={"x-goog-resumable": "start", "Content-Length": "0"})
    with urllib.request.urlopen(start, timeout=60) as r:
        location = r.headers.get("Location") or r.headers.get("location")
    if not location:
        raise OpusError("OpusClip's upload didn't start (no upload address returned).")
    size = Path(path).stat().st_size
    with open(path, "rb") as f:
        put = urllib.request.Request(location, data=f, method="PUT",
                                     headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)})
        with urllib.request.urlopen(put, timeout=3600):
            pass
    return link["uploadId"]


def create_project(source):
    """Start a clipping project from a link or a local file (uses OpusClip credits)."""
    video = upload(source) if Path(source).exists() else source
    project = _api("POST", "/clip-projects", {"videoUrl": video})
    pid = project.get("projectId") or project.get("id")
    if not pid:
        raise OpusError("OpusClip didn't return a project ID.")
    s = _load_state()
    s["projects"] = (s["projects"] + [{"projectId": pid, "source": str(source)[:200], "stage": project.get("stage", "QUEUED"),
                                       "created": datetime.now(timezone.utc).isoformat(), "notified": False}])[-30:]
    _save_state(s)
    return (f"✅ OpusClip is making clips (project {pid}). That usually takes 10 to 30 minutes. "
            "I'll message you when they're ready.")


def clips(project_id):
    """Clips for a project, in OpusClip's order (best first)."""
    rows = _api("GET", "/exportable-clips", query={"q": "findByProjectId", "projectId": project_id,
                                                   "pageNum": 1, "pageSize": 20})
    rows = rows if isinstance(rows, list) else rows.get("data", [])
    out = []
    for c in rows:
        cid = str(c.get("id", ""))
        out.append({"projectId": c.get("projectId") or cid.split(".")[0],
                    "clipId": cid.split(".", 1)[1] if "." in cid else (c.get("curationId") or cid),
                    "title": c.get("title") or "Untitled clip", "seconds": round((c.get("durationMs") or 0) / 1000),
                    "preview": c.get("uriForPreview") or c.get("uriForExport") or "",
                    "description": c.get("description") or "", "hashtags": c.get("hashtags") or ""})
    return out


def _clip_list(items, limit=8):
    lines = []
    for i, c in enumerate(items[:limit], 1):
        lines.append(f"{i}. {c['title']} ({c['seconds']}s)\n   {c['preview']}")
    return "\n".join(lines)


def check_projects(notify=None):
    """Check running projects (the scheduler calls this). Messages you when clips are ready."""
    if not is_configured():
        return 0
    s = _load_state()
    done = 0
    for p in s["projects"]:
        if p.get("notified"):
            continue
        try:
            info = _api("GET", f"/clip-projects/{p['projectId']}")
        except OpusError:
            continue
        p["stage"] = info.get("stage", p.get("stage"))
        if p["stage"] == "COMPLETE":
            items = clips(p["projectId"])
            s["last_clips"] = items
            p["notified"] = True
            done += 1
            if notify:
                notify(f"🎬 Your clips are ready ({len(items)} from {p['source'][:60]}):\n\n{_clip_list(items)}\n\n"
                       "Watch them with the links. To post one: /post 1 youtube instagram (or add 'at 6pm').")
        elif p["stage"] == "STALLED" or info.get("error"):
            p["notified"] = True
            if notify:
                notify(f"⚠️ OpusClip couldn't finish project {p['projectId']}: {info.get('error') or 'it stalled'}. "
                       "Check it on clip.opus.pro.")
    _save_state(s)
    return done


def describe_clips():
    if not is_configured():
        return NOT_CONNECTED
    s = _load_state()
    running = [p for p in s["projects"] if not p.get("notified")]
    parts = []
    if running:
        parts.append("⏳ Being made:\n" + "\n".join(f"• {p['source'][:60]} ({p.get('stage', '?')})" for p in running))
    if s["last_clips"]:
        parts.append("🎬 Latest clips:\n" + _clip_list(s["last_clips"]) +
                     "\n\nTo post one: /post 1 youtube instagram (add 'at 6pm' to schedule)")
    return "\n\n".join(parts) or "No clips yet. Send /clip followed by a video link, or /clip latest."


# ==========================================
# POSTING (always after your Yes)
# ==========================================

def _when(text, now=None):
    """'at 6pm' / 'at 18:30' / 'tomorrow at 9am' / 'in 2 hours' -> future UTC datetime, or None for now."""
    now = now or datetime.now(TZ)
    t = text.lower()
    m = re.search(r"\bin (\d{1,2}) ?(hours?|hrs?|minutes?|mins?)\b", t)
    if m:
        n = int(m.group(1))
        return (now + (timedelta(hours=n) if m.group(2).startswith("h") else timedelta(minutes=n))).astimezone(timezone.utc)
    m = re.search(r"\bat (\d{1,2})(?::(\d{2}))? ?(am|pm)?\b", t)
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and hour < 12:
        hour += 12
    if m.group(3) == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    when = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "tomorrow" in t or when <= now:
        when += timedelta(days=1)
    return when.astimezone(timezone.utc)


def _social_copy(clip, account):
    """OpusClip's own caption for this clip and platform; falls back to the clip's title/description."""
    try:
        job = _api("POST", "/social-copy-jobs", {"projectId": clip["projectId"], "clipId": clip["clipId"],
                                                  "postAccountId": account["postAccountId"],
                                                  "subAccountId": account.get("subAccountId", "")})
        job_id = job["data"]["jobId"]
        for _ in range(20):
            time.sleep(3)
            r = _api("GET", f"/social-copy-jobs/{job_id}").get("data", {})
            if r.get("status") == "COMPLETED":
                return r.get("title") or clip["title"], " ".join(x for x in (r.get("description"), r.get("hashtags")) if x)
            if r.get("status") == "FAILED":
                break
    except (OpusError, KeyError, TypeError):
        pass
    return clip["title"], " ".join(x for x in (clip["description"], clip["hashtags"]) if x)


def plan_post(text, now=None):
    """Turn '/post 2 youtube instagram at 6pm' into a plan, or explain what's missing."""
    if not is_configured():
        return None, NOT_CONNECTED
    s = _load_state()
    m = re.search(r"\b(\d{1,2})\b", re.sub(r"\bat \d.*$|\bin \d.*$", "", text.lower()))
    if not s["last_clips"]:
        return None, "I don't have any clips yet. Make some with /clip first."
    if not m or not 1 <= int(m.group(1)) <= len(s["last_clips"]):
        return None, f"Which clip? Send /post NUMBER PLATFORM, e.g. /post 1 youtube (1 to {len(s['last_clips'])}). /clips lists them."
    clip = s["last_clips"][int(m.group(1)) - 1]
    words = set(re.findall(r"[a-z]+", text.lower()))
    linked = accounts()
    if "all" in words or "everywhere" in words:
        wanted = {a["platform"] for a in linked if a["platform"] != "TWITTER"}
    else:
        wanted = {PLATFORMS[w] for w in words if w in PLATFORMS}
    if not wanted:
        return None, "Where to? e.g. /post 1 youtube instagram tiktok, or /post 1 all"
    targets = [a for a in linked if a["platform"] in wanted]
    missing = wanted - {a["platform"] for a in targets}
    if not targets:
        return None, "None of those accounts are linked in OpusClip. " + test()
    when = _when(text, now)
    posts = []
    for a in targets:
        title, caption = _social_copy(clip, a)
        posts.append({"postAccountId": a["postAccountId"], "subAccountId": a.get("subAccountId", ""),
                      "platform": a["platform"], "account": a.get("extUserName", ""),
                      "title": title[:100], "caption": caption[:2000]})
    plan = {"clip": clip, "posts": posts, "publishAt": when.isoformat().replace("+00:00", "Z") if when else None}
    note = (" (Not linked in OpusClip: " + ", ".join(NICE.get(p, p) for p in missing) + ")") if missing else ""
    return plan, note


def describe_plan(plan):
    when = "now" if not plan["publishAt"] else datetime.fromisoformat(
        plan["publishAt"].replace("Z", "+00:00")).astimezone(TZ).strftime("%a %d %b, %I:%M %p")
    lines = [f"🎬 Content Creator wants to post \"{plan['clip']['title']}\" ({plan['clip']['seconds']}s), {when}:",
             plan["clip"]["preview"]]
    for p in plan["posts"]:
        lines.append(f"\n• {NICE.get(p['platform'], p['platform'])} ({p['account']})\n  Title: {p['title']}\n  Caption: {p['caption'][:300]}")
    if any(p["platform"] == "TWITTER" for p in plan["posts"]):
        lines.append("\nNote: each X post uses 3 OpusClip credits.")
    return "\n".join(lines)


def _ask_owner(msg):
    """Send a Yes/No question to Telegram. Returns True if it was delivered."""
    try:
        from echo_telegram import YES_NO_KEYBOARD, chat_bot_credentials
        token, chat = chat_bot_credentials()
        if not (token and chat):
            return False
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=urllib.parse.urlencode({"chat_id": chat, "text": msg[:4000],
                                                                  "reply_markup": YES_NO_KEYBOARD}).encode())
        with urllib.request.urlopen(req, timeout=30) as r:
            return bool(json.load(r).get("ok"))
    except Exception:
        return False


def propose(kind, data):
    """Save a pending action and ask for Yes/No on Telegram. kind: 'clip' or 'post'."""
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps({"kind": kind, "data": data, "created": datetime.now(timezone.utc).isoformat()}),
                       encoding="utf-8")
    if kind == "clip":
        msg = (f"🎬 Content Creator wants to send this video to OpusClip to make clips:\n{data['source']}\n\n"
               "This uses OpusClip credits (about 1 per minute of video).\n"
               "Only clip videos you own or have permission to use: reposting other people's videos can get "
               "your channels struck.")
    else:
        msg = describe_plan(data)
    msg += "\n\nReply Yes to go ahead, or No to cancel."
    return msg if not _ask_owner(msg) else "I've sent it to your phone. Reply Yes there to go ahead."


def pending():
    try:
        p = json.loads(PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(p["created"])).total_seconds()
    if age > PENDING_MINUTES * 60:
        PENDING.unlink(missing_ok=True)
        return None
    return p


def skip():
    PENDING.unlink(missing_ok=True)
    return "OK, cancelled. Nothing was sent to OpusClip or posted."


def approve():
    p = pending()
    if not p:
        return "That has expired or was already done. Nothing was posted."
    PENDING.unlink(missing_ok=True)
    if p["kind"] == "clip":
        result = create_project(p["data"]["source"])
    else:
        result = publish(p["data"])
    _log(p["kind"], p["data"], result)
    return result


def publish(plan):
    """Post or schedule every post in an approved plan. Reports each one honestly."""
    clip, lines = plan["clip"], []
    for i, p in enumerate(plan["posts"]):
        if i:
            time.sleep(1.2)  # posting endpoints allow 1 request per second
        body = {"projectId": clip["projectId"], "clipId": clip["clipId"], "postAccountId": p["postAccountId"],
                "postDetail": {"title": p["title"], "mediaType": "video",
                               "custom": {"description": p["caption"], "privacy": "public"}}}
        if p.get("subAccountId"):
            body["subAccountId"] = p["subAccountId"]
        name = NICE.get(p["platform"], p["platform"])
        try:
            if plan["publishAt"]:
                _api("POST", "/publish-schedules", {**body, "publishAt": plan["publishAt"]})
                lines.append(f"✅ {name}: scheduled")
            else:
                _api("POST", "/post-tasks", body)
                lines.append(f"✅ {name}: sent to OpusClip for posting")
        except OpusError as exc:
            lines.append(f"❌ {name}: NOT posted ({exc})")
    return "\n".join(lines) + "\n\nOpusClip does the actual upload; it can take a few minutes to appear."


def _log(kind, data, result):
    try:
        log = json.loads(LOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log = []
    log.append({"at": datetime.now(timezone.utc).isoformat(), "kind": kind, "result": result[:500],
                "what": data.get("source") or data.get("clip", {}).get("title")})
    LOG.write_text(json.dumps(log[-200:], indent=2, ensure_ascii=False), encoding="utf-8")


# ==========================================
# TELEGRAM COMMANDS
# ==========================================

def handle(text):
    """Reply for /clip, /clips, /post and /opus. Returns None if the text isn't for OpusClip."""
    t = text.strip()
    low = t.lower()
    if low.startswith("/opus"):
        return describe_accounts()
    if low.startswith("/clips"):
        return describe_clips()
    if low.startswith("/clip"):
        if not is_configured():
            return NOT_CONNECTED
        source = t[5:].strip()
        if source.lower() in ("", "latest", "newest", "last"):
            video = latest_video()
            if not video:
                return (f"Put a video in the content_input folder ({INPUT}) or send /clip followed by a "
                        "YouTube or video link.")
            source = str(video)
        elif not re.match(r"https?://", source) and not Path(source).exists():
            return "Send /clip followed by a video link (YouTube, Drive, Dropbox...), or /clip latest."
        return propose("clip", {"source": source})
    if low.startswith("/post"):
        plan, note = plan_post(t)
        if not plan:
            return note
        return propose("post", plan) + note
    return None
