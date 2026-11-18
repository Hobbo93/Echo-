"""Run your live streams from Telegram (and Echo HQ): OBS does the broadcasting, Echo drives it.

    /live                    dashboard: live or not, how long, scene, stream health, Twitch viewers
    /golive [title]          set the title (if given) and go live; YouTube/TikTok outputs in the
                             Multiple RTMP add-on start with it when "Sync start" is ticked
    /endlive                 end the stream everywhere
    /scenes · /scene NAME    list scenes, switch scene ("/scene brb" finds "Be Right Back")
    /title TEXT · /game NAME change your Twitch title / category
    clip that  (or /clipthat) makes a Twitch clip AND saves the last 30 seconds from OBS, then sends
                             that video to your Telegram (ready for TikTok, Shorts and Reels)

Plain words work too: "go live", "end stream", "clip that", "clip it".
The owner's own command is the Yes for going live; nothing here posts anywhere else by itself.
"""
import re
import shutil
import time
from pathlib import Path

import echo_files
import echo_log
import echo_obs

REPLAY_SECONDS = 30


def _hms(seconds):
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _twitch():
    try:
        import echo_twitch
        return echo_twitch if echo_twitch.is_configured() else None
    except Exception:
        return None


def dashboard():
    lines = []
    try:
        st = echo_obs.status()
        if st["live"]:
            health = "good" if st["dropped_pct"] < 1 else ("shaky" if st["dropped_pct"] < 5 else "BAD")
            lines.append(f"🔴 LIVE for {_hms(st['seconds'])} · scene: {st['scene']}")
            lines.append(f"Stream health: {health} ({st['dropped_pct']}% dropped frames, {st['fps']} fps, CPU {st['cpu']}%)"
                         + (" · reconnecting…" if st["reconnecting"] else ""))
        else:
            lines.append(f"⚫ Not live · OBS ready on scene: {st['scene']}")
        lines.append("Scenes: " + ", ".join(st["scenes"]))
    except echo_obs.OBSError as exc:
        lines.append(f"⚠️ OBS: {exc}")
    tw = _twitch()
    if tw:
        try:
            live = tw.stream()
            lines.append(f"Twitch: {live.get('viewer_count', 0)} watching · {live.get('title', '')}" if live
                         else "Twitch: offline")
        except Exception as exc:
            lines.append(f"Twitch: couldn't check ({str(exc)[:80]})")
    lines.append("/golive · /endlive · /scene NAME · /title TEXT · /game NAME · clip that")
    return "\n".join(lines)


# ==========================================
# REPLAY BUFFER (the local clip that comes to your phone)
# ==========================================

def ensure_replay_buffer():
    """Switch on OBS's replay buffer (last 30 s kept in memory) so 'clip that' can save it. True if running."""
    if echo_obs.call(("GetReplayBufferStatus", None))[0].get("outputActive"):
        return True
    try:
        mode = echo_obs.call(("GetProfileParameter", {"parameterCategory": "Output", "parameterName": "Mode"}))[0]
        section = "AdvOut" if str(mode.get("parameterValue", "")).lower() == "advanced" else "SimpleOutput"
        echo_obs.call(("SetProfileParameter", {"parameterCategory": section, "parameterName": "RecRB",
                                               "parameterValue": "true"}),
                      ("SetProfileParameter", {"parameterCategory": section, "parameterName": "RecRBTime",
                                               "parameterValue": str(REPLAY_SECONDS)}))
        echo_obs.call(("StartReplayBuffer", None))
        return True
    except echo_obs.OBSError as exc:
        echo_log.error("replay buffer", exc)
        return False


def save_replay(wait=8):
    """Save the replay buffer and copy the video into the send-to-phone folder. Returns the file name."""
    if not ensure_replay_buffer():
        raise echo_obs.OBSError("OBS's replay buffer is off. In OBS: Settings > Output > tick 'Enable Replay Buffer', "
                                "then try again.")
    echo_obs.call(("SaveReplayBuffer", None))
    deadline = time.time() + wait
    path = None
    while time.time() < deadline:
        time.sleep(1)
        try:
            path = echo_obs.call(("GetLastReplayBufferReplay", None))[0].get("savedReplayPath")
        except echo_obs.OBSError:
            path = None
        if path and Path(path).exists() and time.time() - Path(path).stat().st_mtime > 1:
            break
    if not path or not Path(path).exists():
        raise echo_obs.OBSError("OBS didn't save the clip in time.")
    echo_files.ensure_folders()
    target = echo_files.OUTBOX / ("Clip " + Path(path).name)
    shutil.copy2(path, target)
    return target.name


def clip_that():
    """Twitch clip (if live and signed in) + local 30-second video to your phone."""
    parts = []
    tw = _twitch()
    if tw:
        try:
            parts.append("🎬 Twitch clip: " + tw.make_clip())
        except Exception as exc:
            parts.append(f"Twitch clip skipped: {str(exc)[:150]}")
    try:
        name = save_replay()
        parts.append(f"📲 Saved the last {REPLAY_SECONDS} seconds from OBS ({name}). It's on its way to this chat.")
    except echo_obs.OBSError as exc:
        parts.append(f"OBS clip skipped: {exc}")
    return "\n".join(parts)


# ==========================================
# COMMANDS (Telegram and Echo HQ)
# ==========================================

def go_live(title=""):
    out = []
    tw = _twitch()
    if title and tw:
        try:
            out.append(tw.set_title(title))
        except Exception as exc:
            out.append(f"Title not changed: {str(exc)[:150]}")
    st = echo_obs.status()
    if st["live"]:
        return "\n".join(out + [f"You're already live ({_hms(st['seconds'])})."])
    ensure_replay_buffer()
    echo_obs.start()
    return "\n".join(out + [f"🔴 Going live now on scene '{st['scene']}'. /live in a moment for viewers and health. "
                            "/endlive to stop."])


def end_live():
    st = echo_obs.status()
    if not st["live"]:
        return "You're not live right now."
    echo_obs.stop()
    return f"⚫ Stream ended after {_hms(st['seconds'])}. Your clips will come through after the stream."


CLIP_WORDS = re.compile(r"^\s*(/clipthat|clip (that|it|this)|clip the last)\b", re.I)


def handle(text):
    """Reply for live-stream commands, or None if the message isn't one."""
    t = text.strip()
    low = t.lower()
    try:
        if low in ("/live", "live status", "stream status"):
            return dashboard()
        m = re.match(r"^/golive\b\s*(.*)$", t, re.I)
        if m:
            return go_live(m.group(1).strip())
        if re.match(r"^go live( now)?[.!]*$", low):  # exact words only, so chat about going live never starts one
            return go_live()
        if re.match(r"^(/endlive|(end|stop) (the |my )?stream( now)?[.!]*|end live)$", low):
            return end_live()
        if low.startswith("/scenes"):
            st = echo_obs.status()
            return f"Scenes (now: {st['scene']}): " + ", ".join(st["scenes"]) + "\nSend /scene and a name."
        m = re.match(r"^/scene\s+(.+)$", t, re.I)
        if m:
            return f"🎬 Switched to scene: {echo_obs.switch(m.group(1))}"
        if CLIP_WORDS.match(t):
            return clip_that()
        m = re.match(r"^/title\s+(.+)$", t, re.I)
        if m:
            tw = _twitch()
            return tw.set_title(m.group(1).strip()) if tw else "Connect Twitch first: /connect 6."
        m = re.match(r"^/game\s+(.+)$", t, re.I)
        if m:
            tw = _twitch()
            return tw.set_game(m.group(1).strip()) if tw else "Connect Twitch first: /connect 6."
    except echo_obs.OBSError as exc:
        return f"⚠️ {exc}"
    except Exception as exc:
        echo_log.error("live", exc)
        return f"Live-stream problem: {str(exc)[:200]}"
    return None
