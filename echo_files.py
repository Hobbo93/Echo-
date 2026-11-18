"""Files between your phone and the PC, through the Echo Telegram chat bot.

Phone -> PC: send Echo a video, file, PDF or audio on Telegram. It is saved to
             %USERPROFILE%\\Echo_inbox (photos and voice notes keep their own handling).
             /files lists them; /get 3 sends number 3 back to your phone.
PC -> phone: drop any file into %USERPROFILE%\\Echo_send_to_phone and Echo sends it to your
             Telegram within a few seconds, then moves it into the "sent" folder inside.

Telegram limits for bots: Echo can receive files up to 20 MB and send files up to 50 MB.
Both folders live outside the Echo folder, so nothing personal ever goes to GitHub.
"""
import re
import time
from datetime import datetime
from pathlib import Path

INBOX = Path.home() / "Echo_inbox"
OUTBOX = Path.home() / "Echo_send_to_phone"
SENT = OUTBOX / "sent"
RECEIVE_LIMIT = 20 * 1024 * 1024
SEND_LIMIT = 50 * 1024 * 1024

VIDEO = {".mp4", ".mov", ".m4v"}
AUDIO = {".mp3", ".m4a", ".wav", ".aac", ".flac"}
PHOTO = {".jpg", ".jpeg", ".png"}


def ensure_folders():
    for folder in (INBOX, OUTBOX, SENT):
        folder.mkdir(parents=True, exist_ok=True)


def incoming(msg):
    """(file_id, file name, size, kind) for a video, file, PDF or audio message; None for anything else.
    Photos (and image files) and voice notes are left to the existing photo and voice handling."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    for kind in ("video", "video_note", "animation", "audio", "document"):
        item = msg.get(kind)
        if not item:
            continue
        if kind == "document" and str(item.get("mime_type", "")).startswith("image/"):
            return None  # photos sent as files: handled by handle_photo
        default_ext = {"video": ".mp4", "video_note": ".mp4", "animation": ".mp4", "audio": ".mp3"}.get(kind, "")
        name = item.get("file_name") or f"{kind}-{stamp}{default_ext}"
        return item.get("file_id"), name, int(item.get("file_size") or 0), kind
    return None


def _safe_name(name):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(name).name).strip(" .") or "file"
    return name[:120]


def save_incoming(data, name):
    """Save bytes into the inbox without overwriting an earlier file. Returns the path."""
    ensure_folders()
    path = INBOX / _safe_name(name)
    n = 2
    while path.exists():
        path = INBOX / f"{Path(_safe_name(name)).stem} ({n}){Path(name).suffix}"
        n += 1
    path.write_bytes(data)
    return path


def inbox_files():
    """Inbox files, newest first."""
    ensure_folders()
    files = [p for p in INBOX.iterdir() if p.is_file()]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def _size(n):
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def list_text(limit=15):
    files = inbox_files()
    if not files:
        return ("📂 Nothing here yet. Send me a video, file or PDF and I'll save it on the PC.\n"
                f"To send something from the PC to your phone, drop it in {OUTBOX}")
    lines = [f"📂 Files you've sent me (saved in {INBOX}):"]
    for i, p in enumerate(files[:limit], 1):
        when = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d %b %H:%M")
        lines.append(f"{i}. {p.name} ({_size(p.stat().st_size)}, {when})")
    if len(files) > limit:
        lines.append(f"…and {len(files) - limit} older.")
    lines.append("Send /get and a number to get one back on your phone.")
    return "\n".join(lines)


def pick(n):
    files = inbox_files()
    return files[n - 1] if 1 <= n <= len(files) else None


def ready_to_send(settle=3):
    """Files dropped in the send-to-phone folder that have finished copying (unchanged for a few seconds)."""
    ensure_folders()
    now = time.time()
    return sorted((p for p in OUTBOX.iterdir()
                   if p.is_file() and not p.name.startswith(("~", ".")) and p.suffix.lower() not in (".tmp", ".crdownload", ".part")
                   and now - p.stat().st_mtime >= settle),
                  key=lambda p: p.stat().st_mtime)


def mark_sent(path):
    ensure_folders()
    target = SENT / path.name
    n = 2
    while target.exists():
        target = SENT / f"{path.stem} ({n}){path.suffix}"
        n += 1
    path.replace(target)
    return target


def upload_method(path):
    """(Telegram method, form field, content type) for sending this file."""
    ext = path.suffix.lower()
    if ext in PHOTO and path.stat().st_size <= 9 * 1024 * 1024:
        return "sendPhoto", "photo", "image/png" if ext == ".png" else "image/jpeg"
    if ext in VIDEO:
        return "sendVideo", "video", "video/mp4"
    if ext in AUDIO:
        return "sendAudio", "audio", "audio/mpeg"
    return "sendDocument", "document", "application/octet-stream"
