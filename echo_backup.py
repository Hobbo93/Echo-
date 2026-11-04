"""Nightly backups of everything Echo has learned and recorded.

What's saved: memory (chats, facts, research), approvals and tasks, schedule, personality,
growth and brain settings, business records, trading journal, Roblox maps.
What's NOT saved: your keys and passwords (.echo_telegram.json), so they never end up in a
cloud folder. Keep those safe yourself; connect_echo.bat can always re-enter them.

Where: a folder called Echo_backups in your OneDrive, Dropbox or Google Drive folder if the PC
has one (so it's copied off the PC for free), otherwise in Documents. The last 14 are kept.
/backup on Telegram backs up now. To restore, unzip a backup: each file shows where it goes.
Standard library only.
"""
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
STATE = HOME / ".echo_backup.json"
KEEP = 14
MAX_FOLDER_MB = 200  # skip a folder if it's bigger than this (e.g. lots of photos or videos)

# (where it lives, name inside the zip)
FILES = [
    (ROOT / "echo_memory.db", "echo_folder/echo_memory.db"),
    (ROOT / "echo_approvals.db", "echo_folder/echo_approvals.db"),
    (ROOT / "echo_approvals.json", "echo_folder/echo_approvals.json"),
    (ROOT / "echo_tasks.json", "echo_folder/echo_tasks.json"),
    (ROOT / "echo_schedule.json", "echo_folder/echo_schedule.json"),
    (HOME / ".echo_personality.json", "user_folder/.echo_personality.json"),
    (HOME / ".echo_growth.json", "user_folder/.echo_growth.json"),
    (HOME / ".echo_brain.json", "user_folder/.echo_brain.json"),
]
FOLDERS = [
    (HOME / "Echo_business", "user_folder/Echo_business"),
    (HOME / "Echo_trading", "user_folder/Echo_trading"),
    (HOME / "Echo_roblox" / "maps", "user_folder/Echo_roblox/maps"),
]
NEVER = {".echo_telegram.json", ".echo_shopify_token.json"}  # keys and passwords stay off backups


def _state():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def destination():
    """Echo_backups inside a cloud-synced folder if there is one, else Documents."""
    custom = _state().get("folder")
    if custom:
        return Path(custom)
    candidates = [os.getenv("OneDrive"), os.getenv("OneDriveConsumer"), HOME / "OneDrive", HOME / "Dropbox",
                  HOME / "Google Drive" / "My Drive", Path("G:/My Drive"), HOME / "Google Drive"]
    for c in candidates:
        if c and Path(c).is_dir():
            return Path(c) / "Echo_backups"
    return HOME / "Documents" / "Echo_backups"


def _folder_mb(folder):
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1e6


def _add_db(z, src, name):
    """Copy a SQLite database safely even while Echo is using it."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.db"
        live, out = sqlite3.connect(src), sqlite3.connect(copy)
        try:
            live.backup(out)
        finally:
            out.close()
            live.close()
        z.write(copy, name)


def backup_now(dest=None):
    """Make one backup. Returns (zip path, summary text)."""
    dest = Path(dest or destination())
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"echo_backup_{datetime.now():%Y-%m-%d_%H%M}.zip"
    saved, skipped = 0, []
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for src, name in FILES:
            if src.name in NEVER or not src.is_file():
                continue
            if src.suffix == ".db":
                _add_db(z, src, name)
            else:
                z.write(src, name)
            saved += 1
        for folder, name in FOLDERS:
            if not folder.is_dir():
                continue
            if _folder_mb(folder) > MAX_FOLDER_MB:
                skipped.append(folder.name)
                continue
            for f in folder.rglob("*"):
                if f.is_file() and f.name not in NEVER:
                    z.write(f, f"{name}/{f.relative_to(folder).as_posix()}")
                    saved += 1
        z.writestr("README.txt", "Echo backup made " + datetime.now().strftime("%d %b %Y %H:%M") +
                   ".\nRestore: close Echo, then copy echo_folder/* into the Echo folder and user_folder/* into "
                   "your user folder (C:\\Users\\<you>). Keys and passwords are not in backups: run "
                   "connect_echo.bat to enter them again.\n")
    old = sorted(dest.glob("echo_backup_*.zip"))[:-KEEP]
    for f in old:
        f.unlink(missing_ok=True)
    s = _state()
    s["last"] = datetime.now().isoformat(timespec="minutes")
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    size = path.stat().st_size / 1e6
    text = f"💾 Backed up {saved} files ({size:.1f} MB) to {path}"
    if skipped:
        text += f"\nSkipped (over {MAX_FOLDER_MB} MB): {', '.join(skipped)}"
    return path, text


def due(now=None, hour=1):
    """Once a day, from 1 AM (or straight away if the last backup is over a day old)."""
    now = now or datetime.now()
    last = _state().get("last")
    if not last:
        return True
    try:
        last = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (now - last).total_seconds() > 86400 or (last.date() < now.date() and now.hour >= hour)


def last_backup():
    return _state().get("last", "")
