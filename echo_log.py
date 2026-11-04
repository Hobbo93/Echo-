"""Echo's error log: problems get written down instead of disappearing.

Every part of Echo calls error(where, exc) when something goes wrong. The log lives in
%USERPROFILE%\\Echo_logs\\errors.log (about 1 MB max, the previous one kept as errors.1.log).
summary() is what /errors and the morning problem report on Telegram show.
Anything that looks like a key or token is blanked out before it's written.
Standard library only.
"""
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path.home() / "Echo_logs"
MAX_BYTES = 1_000_000
_lock = threading.Lock()
_SECRET = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b|shpat_\w+|shpss_\w+|sk-[A-Za-z0-9_-]{10,}|"
                     r"(?i:(?:password|passwd|secret|token|api[_-]?key|authorization)[\"']?\s*[:=]\s*)\S+")


def log_file():
    return LOG_DIR / "errors.log"


def _process():
    return Path(sys.argv[0]).stem or "echo"


def _clean(text):
    text = _SECRET.sub("[hidden]", str(text))
    return " ".join(text.split())[:500]


def error(where, exc=None, note=""):
    """Write one problem down. Never raises."""
    try:
        what = note or ""
        if exc is not None:
            what = (what + ": " if what else "") + f"{type(exc).__name__}: {exc}"
        line = "\t".join([datetime.now().isoformat(timespec="seconds"), _process(), _clean(where), _clean(what)])
        with _lock:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            f = log_file()
            if f.exists() and f.stat().st_size > MAX_BYTES:
                f.replace(LOG_DIR / "errors.1.log")
            with open(f, "a", encoding="utf-8") as out:
                out.write(line + "\n")
    except Exception:
        pass  # logging must never break Echo


def install():
    """Log crashes in this program and its threads (call once at start-up)."""
    old = sys.excepthook

    def hook(kind, value, tb):
        where = traceback.extract_tb(tb)[-1] if tb else None
        error(f"crash in {Path(where.filename).name}:{where.lineno}" if where else "crash", value)
        old(kind, value, tb)
    sys.excepthook = hook

    def thread_hook(args):
        if args.exc_type is SystemExit:
            return
        where = traceback.extract_tb(args.exc_traceback)[-1] if args.exc_traceback else None
        error(f"crash in {Path(where.filename).name}:{where.lineno}" if where else "thread crash", args.exc_value)
    threading.excepthook = thread_hook


def recent(hours=24):
    """Problems from the last few hours: [{'at', 'process', 'where', 'what'}], oldest first."""
    cutoff = datetime.now() - timedelta(hours=hours)
    out = []
    for f in (LOG_DIR / "errors.1.log", log_file()):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            try:
                at = datetime.fromisoformat(parts[0])
            except ValueError:
                continue
            if at >= cutoff:
                out.append({"at": at, "process": parts[1], "where": parts[2], "what": parts[3]})
    return out


def summary(hours=24, limit=8):
    """Short report grouped by problem, or '' if nothing went wrong."""
    rows = recent(hours)
    if not rows:
        return ""
    groups = {}
    for r in rows:
        g = groups.setdefault(r["where"], {"count": 0, "last": r})
        g["count"] += 1
        g["last"] = r
    ranked = sorted(groups.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    lines = [f"⚠️ {len(rows)} problem{'s' if len(rows) != 1 else ''} in the last {hours} hours:"]
    for where, g in ranked[:limit]:
        last = g["last"]
        lines.append(f"• {where} ({last['process']}) ×{g['count']}, last at {last['at']:%H:%M}: {last['what'][:160]}")
    if len(ranked) > limit:
        lines.append(f"…and {len(ranked) - limit} more kinds. Full list: {log_file()}")
    lines.append("Send these to Claude if you want them fixed.")
    return "\n".join(lines)


def since_last_report(state, now=None):
    """For the morning report: the summary once a day, only if something went wrong."""
    now = now or time.time()
    day = datetime.fromtimestamp(now).date().isoformat()
    if state.get("last_error_report") == day:
        return ""
    state["last_error_report"] = day
    return summary(24)
