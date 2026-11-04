"""Echo's health check: tests every part of itself and says plainly what needs fixing.

/health on Telegram runs it now; every Sunday at 10 AM it's sent automatically.
Checks: Echo's parts are running, the AI (Ollama) and its models, what's connected,
problems in the error log this week, the last backup, and free disk space.
Standard library only; nothing is changed, it only looks.
"""
import shutil
from datetime import datetime
from pathlib import Path

OK, WARN, BAD = "🟢", "🟡", "🔴"


def _check(fn):
    try:
        return fn()
    except Exception as exc:
        return [(WARN, f"Couldn't check: {str(exc)[:120]}")]


def parts():
    import echo_business
    out = []
    for line in echo_business.status_text().splitlines()[1:]:
        if line.strip() and "Ollama" not in line:  # the AI brain has its own section
            level = line[:1] if line[:1] in (OK, BAD) else WARN
            out.append((level, line[1:].strip()))
    return out


def brain():
    import echo_brain
    import echo_connections
    if not echo_connections._ollama():
        return [(BAD, "The AI (Ollama) isn't running. Fix: open the Ollama app on the PC.")]
    have = echo_brain.installed()
    out = []
    for label, name, fix in (("Main AI", echo_brain.model(), f"Fix: send /brain upgrade, or run: ollama pull {echo_brain.model()}"),
                             ("Photo AI", echo_brain.vision_model(), "Fix: send /getvision")):
        found = any(h == name or h == name + ":latest" for h in have)
        out.append((OK, f"{label}: {name}") if found else
                   (WARN if label == "Photo AI" else BAD, f"{label} {name} isn't downloaded. {fix}"))
    return out


def connections():
    import echo_connections
    rows = [r for r in echo_connections.check_all(live=False)  # the AI and photo brain have their own section;
            if r["service"] not in ("Ollama on this PC", "Vision model", "Base44")]  # Base44 works through Claude
    on = [r["service"] for r in rows if r["ok"]]
    off = [r for r in rows if not r["ok"]]
    out = [(OK, "Connected: " + (", ".join(on) or "nothing yet"))]
    if off:
        out.append((WARN, "Not connected yet: " + ", ".join(r["service"] for r in off) +
                    ". Fix: double-click connect_echo.bat (or ask \"what's connected?\" for steps)."))
    return out


def errors():
    import echo_log
    rows = echo_log.recent(24 * 7)
    if not rows:
        return [(OK, "No problems logged this week.")]
    kinds = {}
    for r in rows:
        kinds[r["where"]] = kinds.get(r["where"], 0) + 1
    top = ", ".join(f"{k} ×{n}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])[:4])
    level = BAD if len(rows) >= 50 else WARN
    return [(level, f"{len(rows)} problems logged this week (most: {top}). Details: /errors")]


def backup(now=None):
    import echo_backup
    last = echo_backup.last_backup()
    if not last:
        return [(WARN, "No backup yet. Fix: send /backup (it also runs every night).")]
    days = ((now or datetime.now()) - datetime.fromisoformat(last)).days
    if days >= 3:
        return [(BAD, f"Last backup was {days} days ago. Fix: send /backup, and check the PC stays on.")]
    return [(OK, f"Last backup: {last.replace('T', ' ')}")]


def disk(path=None):
    free_gb = shutil.disk_usage(path or Path.home()).free / 1e9
    if free_gb < 5:
        return [(BAD, f"Only {free_gb:.1f} GB free on the disk. Fix: delete old videos or downloads.")]
    if free_gb < 20:
        return [(WARN, f"{free_gb:.0f} GB free on the disk: getting low.")]
    return [(OK, f"{free_gb:.0f} GB free on the disk.")]


SECTIONS = [("Echo's parts", parts), ("AI brain", brain), ("Connections", connections),
            ("Problems", errors), ("Backups", backup), ("Disk", disk)]


def report():
    lines, worst = [], OK
    for title, fn in SECTIONS:
        lines.append(f"\n{title}")
        for level, text in _check(fn):
            lines.append(f"{level} {text}")
            if level == BAD or (level == WARN and worst == OK):
                worst = level
    head = {OK: "✅ Echo health check: everything looks good.",
            WARN: "🩺 Echo health check: working, with a few things to sort out.",
            BAD: "🩺 Echo health check: something needs fixing."}[worst]
    return head + "\n" + "\n".join(lines)
