"""Echo and your Twitch channel. Connect with /connect 6 on Telegram (or connect_echo.bat).

    Live alerts      a message on your phone when your stream starts (title, game, link) and when it
                     ends (how long, peak viewers)
    Clips            after each stream: the top clips and the VOD, with 3 short-video ideas from the
                     Content Creator. If OpusClip is connected, it offers to cut the VOD into clips
                     (that only happens after your Yes, like every other outside action).
    Stats            /twitch any time; a weekly report on Monday morning (followers, streams, hours,
                     peak viewers, top clips)
    Chat bot         /twitch bot on: Echo answers viewers in your Twitch chat when they type !echo
                     (or !ask) and a question, or @mention it. You switch it on yourself and can switch
                     it off any time (/twitch bot off). It never promises, buys, posts or links anything.

Needs a free Twitch app (dev.twitch.tv/console): Client ID + Client secret, and your channel name.
The chat bot also signs in to Twitch once (twitch.tv/activate). Keys and tokens are saved only in
%USERPROFILE%\\.echo_telegram.json; nothing secret goes in the Echo folder or its memory.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import echo_business
import echo_connect
import echo_log

HELIX = "https://api.twitch.tv/helix"
ID = "https://id.twitch.tv/oauth2"
CHECK_EVERY = 120          # seconds between live checks
CHAT_SCOPES = "chat:read chat:edit"
STATE = "twitch"           # echo_business.load/save name (no secrets in here)

_app_token = {"token": "", "until": 0.0}
_last_check = [0.0]
_login_thread = {"t": None}


class TwitchError(RuntimeError):
    pass


# ==========================================
# SETTINGS AND HTTP
# ==========================================

def _cfg():
    return echo_connect._cfg()


def channel():
    return str(_cfg().get("twitch_channel", "")).strip().lower().lstrip("@")


def is_configured():
    c = _cfg()
    return all(str(c.get(k, "")).strip() for k in ("twitch_client_id", "twitch_client_secret", "twitch_channel"))


def state():
    s = echo_business.load(STATE, {})
    return s if isinstance(s, dict) else {}


def save_state(s):
    echo_business.save(STATE, s)


def _request(url, data=None, headers=None, method=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, body, headers or {}, method=method or ("POST" if body else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace"))
        except ValueError:
            detail = {}
        err = TwitchError(detail.get("message") or f"Twitch error {exc.code}")
        err.code, err.detail = exc.code, detail
        raise err from None


def app_token():
    """App access token (client credentials), cached until shortly before it expires."""
    if _app_token["token"] and time.time() < _app_token["until"]:
        return _app_token["token"]
    c = _cfg()
    got = _request(ID + "/token", {"client_id": c.get("twitch_client_id", ""),
                                   "client_secret": c.get("twitch_client_secret", ""),
                                   "grant_type": "client_credentials"})
    _app_token.update(token=got["access_token"], until=time.time() + int(got.get("expires_in", 3600)) - 300)
    return _app_token["token"]


def helix(path, **query):
    url = HELIX + path + ("?" + urllib.parse.urlencode(query) if query else "")
    headers = {"Client-Id": _cfg().get("twitch_client_id", ""), "Authorization": "Bearer " + app_token()}
    try:
        return _request(url, headers=headers)
    except TwitchError as exc:
        if getattr(exc, "code", 0) != 401:
            raise
        _app_token["token"] = ""  # expired early: get a new one and try once more
        headers["Authorization"] = "Bearer " + app_token()
        return _request(url, headers=headers)


def user():
    """{'id', 'login', 'display_name'} for your channel (cached in state)."""
    s = state()
    if s.get("user", {}).get("login") == channel():
        return s["user"]
    data = helix("/users", login=channel()).get("data") or []
    if not data:
        raise TwitchError(f"I couldn't find a Twitch channel called '{channel()}'.")
    s["user"] = {k: data[0][k] for k in ("id", "login", "display_name")}
    save_state(s)
    return s["user"]


def test():
    u = user()
    live = stream()
    return f"Found your channel {u['display_name']} ({'live now' if live else 'offline'})."


# ==========================================
# LIVE ALERTS
# ==========================================

def stream():
    """Your live stream right now, or None."""
    data = helix("/streams", user_login=channel()).get("data") or []
    return data[0] if data else None


def _parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _hm(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def tick(notify, now=None, force=False):
    """Called from the scheduler every minute. Checks Twitch every 2 minutes and sends alerts."""
    if not is_configured():
        return
    t = now or time.time()
    if not force and t - _last_check[0] < CHECK_EVERY:
        return
    _last_check[0] = t
    live = stream()
    s = state()
    session = s.get("session")
    if live and not session:
        s["session"] = {"started": live["started_at"], "title": live.get("title", ""),
                        "game": live.get("game_name", ""), "peak": int(live.get("viewer_count", 0))}
        save_state(s)
        notify(f"🔴 You're live on Twitch!\n{live.get('title', '')}"
               + (f"\nPlaying: {live['game_name']}" if live.get("game_name") else "")
               + f"\nhttps://twitch.tv/{channel()}")
    elif live and session:
        session["peak"] = max(int(session.get("peak", 0)), int(live.get("viewer_count", 0)))
        session["title"] = live.get("title", session.get("title", ""))
        save_state(s)
    elif not live and session:
        started = _parse(session["started"])
        ended = datetime.now(timezone.utc)
        session.update(ended=ended.isoformat(), seconds=int((ended - started).total_seconds()))
        s["history"] = (s.get("history", []) + [session])[-60:]
        s["session"] = None
        save_state(s)
        notify(f"⚫ Stream ended after {_hm(session['seconds'])}. Peak viewers: {session['peak']}.\n"
               "I'm gathering your clips for the Content Creator…")
        try:
            notify(after_stream(session))
        except Exception as exc:
            echo_log.error("twitch clips", exc)


# ==========================================
# CLIPS FOR THE CONTENT CREATOR
# ==========================================

def top_clips(since, limit=3):
    data = helix("/clips", broadcaster_id=user()["id"], started_at=since, first=20).get("data") or []
    return sorted(data, key=lambda c: c.get("view_count", 0), reverse=True)[:limit]


def latest_vod():
    data = helix("/videos", user_id=user()["id"], type="archive", first=1).get("data") or []
    return data[0] if data else None


def _ideas(session, clips):
    titles = "; ".join(c.get("title", "") for c in clips) or "no clips yet"
    try:
        return echo_business.ask_ai(
            f"A Twitch streamer just finished a stream titled '{session.get('title', '')}' "
            f"({session.get('game', '')}). Clip titles: {titles}. Give 3 short-video ideas for TikTok, YouTube "
            "Shorts and Instagram Reels from this stream: for each a hook (first 2 seconds) and a caption. "
            "Be brief. Don't invent things that happened on stream beyond the titles.",
            system="You are the Content Creator in Echo's office. Short, practical, no hashtag spam.",
            timeout=180)
    except Exception:
        return ""


def after_stream(session):
    """Message with the top clips, the VOD and video ideas; offers OpusClip if it's connected."""
    clips = top_clips(session["started"])
    vod = latest_vod()
    lines = ["🎬 Content Creator: your stream, ready to repurpose."]
    if clips:
        lines.append("Top clips:")
        lines += [f"{i}. {c.get('title', 'Clip')} ({c.get('view_count', 0)} views) {c.get('url', '')}"
                  for i, c in enumerate(clips, 1)]
    else:
        lines.append("No clips were made this stream. Tip: viewers (or you) press the clip button on great moments.")
    if vod:
        lines.append(f"Full VOD: {vod.get('url', '')}")
    ideas = _ideas(session, clips)
    if ideas:
        lines += ["", "Ideas:", ideas.strip()[:1500]]
    try:
        import echo_opusclip
        if vod and echo_opusclip.is_configured():
            lines += ["", echo_opusclip.propose("clip", {"source": vod["url"]})]
        elif vod:
            lines += ["", "Connect OpusClip (/connect 1) and I'll cut the VOD into clips for you after your Yes."]
    except Exception as exc:
        echo_log.error("twitch opusclip", exc)
    return "\n".join(lines)


# ==========================================
# STATS
# ==========================================

def followers():
    return int(helix("/channels/followers", broadcaster_id=user()["id"]).get("total", 0))


def stats(days=7):
    s = state()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    recent = [x for x in s.get("history", []) if x.get("ended") and _parse(x["ended"]) >= since]
    hours = sum(x.get("seconds", 0) for x in recent) / 3600
    peak = max((x.get("peak", 0) for x in recent), default=0)
    total = followers()
    last = s.get("last_followers")
    s["last_followers"] = total
    save_state(s)
    change = f" ({total - last:+d} since last report)" if isinstance(last, int) else ""
    lines = [f"📊 Twitch: {user()['display_name']} (last {days} days)",
             f"Followers: {total:,}{change}",
             f"Streams: {len(recent)} · {hours:.1f} hours · best peak: {peak} viewers"]
    if s.get("session"):
        lines.append(f"🔴 Live now: {s['session'].get('title', '')} (peak so far {s['session'].get('peak', 0)})")
    best = top_clips(since.isoformat().replace("+00:00", "Z"), limit=3)
    if best:
        lines.append("Top clips: " + "; ".join(f"{c.get('title', 'Clip')} ({c.get('view_count', 0)})" for c in best))
    return "\n".join(lines)


def weekly_due(schedule, now):
    """Monday from 9 AM, once a week."""
    week = now.strftime("%G-W%V")
    return now.weekday() == 0 and now.hour >= 9 and schedule.get("last_twitch_report") != week, week


# ==========================================
# CHAT BOT SIGN-IN (Twitch device login) AND SWITCH
# ==========================================

def bot_enabled():
    return bool(state().get("bot_on"))


def set_bot(on):
    s = state()
    s["bot_on"] = bool(on)
    save_state(s)


def chat_token():
    """(access token, login) for the account that talks in chat, refreshing it if needed; ('', '') if none."""
    c = _cfg()
    token = str(c.get("twitch_chat_token", "")).strip()
    if not token:
        return "", ""
    try:
        info = _request(ID + "/validate", headers={"Authorization": "OAuth " + token})
        return token, info.get("login", "")
    except TwitchError:
        pass
    refresh = str(c.get("twitch_chat_refresh", "")).strip()
    if not refresh:
        return "", ""
    got = _request(ID + "/token", {"grant_type": "refresh_token", "refresh_token": refresh,
                                   "client_id": c.get("twitch_client_id", ""),
                                   "client_secret": c.get("twitch_client_secret", "")})
    echo_connect._save_setting("twitch_chat_token", got["access_token"])
    if got.get("refresh_token"):
        echo_connect._save_setting("twitch_chat_refresh", got["refresh_token"])
    info = _request(ID + "/validate", headers={"Authorization": "OAuth " + got["access_token"]})
    return got["access_token"], info.get("login", "")


def start_login(notify):
    """Start Twitch's device sign-in for the chat bot. Returns the message with the code to enter."""
    c = _cfg()
    got = _request(ID + "/device", {"client_id": c.get("twitch_client_id", ""), "scopes": CHAT_SCOPES})

    def wait():
        deadline = time.time() + int(got.get("expires_in", 1800))
        while time.time() < deadline:
            time.sleep(max(5, int(got.get("interval", 5))))
            try:
                tok = _request(ID + "/token", {"client_id": c.get("twitch_client_id", ""), "scopes": CHAT_SCOPES,
                                               "device_code": got["device_code"],
                                               "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            except TwitchError as exc:
                if "pending" in str(getattr(exc, "detail", {}).get("message", exc)).lower():
                    continue
                notify("🔴 Twitch sign-in for the chat bot didn't work: " + str(exc)[:200] + ". Send /twitch bot on to try again.")
                return
            echo_connect._save_setting("twitch_chat_token", tok["access_token"])
            echo_connect._save_setting("twitch_chat_refresh", tok.get("refresh_token", ""))
            set_bot(True)
            notify("🟢 Twitch chat bot signed in and switched on. Viewers can type !echo and a question. "
                   "/twitch bot off to stop it.")
            return
        notify("The Twitch sign-in code expired. Send /twitch bot on to get a new one.")

    t = threading.Thread(target=wait, daemon=True)
    _login_thread["t"] = t
    t.start()
    return (f"🤖 To let Echo talk in your Twitch chat:\n1. Open {got.get('verification_uri', 'https://www.twitch.tv/activate')}\n"
            f"2. Sign in as the account that should talk in chat (your own, or a separate bot account)\n"
            f"3. Enter the code {got['user_code']} and tap Authorize.\nI'll tell you here when it's on.")


# ==========================================
# TELEGRAM COMMANDS
# ==========================================

def handle(text, notify):
    """/twitch, /twitch clips, /twitch bot on|off. Returns a reply, or None if the text isn't for Twitch."""
    low = text.strip().lower()
    if not low.startswith("/twitch"):
        return None
    if not is_configured():
        return "Twitch isn't connected yet. Send /connect 6 and I'll walk you through it (about 3 minutes)."
    try:
        if low.startswith("/twitch bot off"):
            set_bot(False)
            return "⏸️ The Twitch chat bot is off. /twitch bot on to switch it back on."
        if low.startswith("/twitch bot"):
            token, login = chat_token()
            if token:
                set_bot(True)
                return (f"🟢 Twitch chat bot is on, talking as {login} in twitch.tv/{channel()}. Viewers type !echo "
                        "and a question. /twitch bot off to stop it.")
            return start_login(notify)
        if low.startswith("/twitch clips"):
            since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat().replace("+00:00", "Z")
            clips = top_clips(since, limit=5)
            if not clips:
                return "No Twitch clips in the last 7 days."
            return "🎬 Your top clips this week:\n" + "\n".join(
                f"{i}. {c.get('title', 'Clip')} ({c.get('view_count', 0)} views) {c.get('url', '')}"
                for i, c in enumerate(clips, 1)) + "\nSend /clip and a link to have the Content Creator cut one."
        return stats() + "\n\nChat bot: " + ("on" if bot_enabled() else "off") + \
            " · /twitch clips · /twitch bot on|off"
    except TwitchError as exc:
        return f"Twitch problem: {str(exc)[:200]}"
