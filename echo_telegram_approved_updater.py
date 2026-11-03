"""Echo approval-gated GitHub updater. Standard library only.
Start with: py echo_telegram_approved_updater.py
Uses the same Telegram settings as notifications: ECHO_TELEGRAM_TOKEN /
ECHO_TELEGRAM_CHAT_ID env vars or ~/.echo_telegram.json (see TELEGRAM_SETUP.md).
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

from echo_telegram import _credentials, shared_bot, DECISION_FILE

REPO_URL = "https://github.com/Hobbo93/Echo-.git"
ROOT = Path(__file__).resolve().parent
TOKEN, CHAT_ID = _credentials()
STATE_FILE = Path.home() / ".echo_approved_update_state.json"
BACKUPS = Path.home() / "Echo_update_backups"
IGNORED = {".git", ".env", "venv", ".venv", "__pycache__", "node_modules"}

def telegram(method, params):
    url = "https://api.telegram.org/bot" + TOKEN + "/" + method
    body = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=body, timeout=40) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        try:
            description = json.loads(details).get("description", "Unknown Telegram error")
        except ValueError:
            description = "Unknown Telegram error"
        raise RuntimeError(f"Telegram {method}: HTTP {exc.code}: {description}") from None
    if not data.get("ok"):
        raise RuntimeError("Telegram request failed")
    return data["result"]

def notify(message):
    return telegram("sendMessage", {"chat_id": CHAT_ID, "text": message[:4000]})

def git(*args, directory=None):
    result = subprocess.run(
        ["git", *args], cwd=directory, text=True,
        capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1000:])
    return result.stdout.strip()

def snapshot():
    temp = Path(tempfile.mkdtemp(prefix="echo_approved_"))
    try:
        repo = temp / "repo"
        git("clone", "--quiet", "--depth", "1", "--branch", "main", REPO_URL, str(repo))
        return temp, repo, git("rev-parse", "HEAD", directory=repo)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

def included_files(repo):
    items = {}
    for source in repo.rglob("*"):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(repo)
        if any(part in IGNORED or part.startswith(".echo_") for part in relative.parts):
            continue
        items[relative.as_posix()] = source
    return items

def target_file(name):
    dest = (ROOT / name).resolve()
    if not dest.is_relative_to(ROOT):
        raise RuntimeError("Unsafe destination")
    return dest

def install(repo, commit):
    sources = included_files(repo)
    changes = []
    for name, source in sources.items():
        destination = target_file(name)
        if not destination.exists() or destination.read_bytes() != source.read_bytes():
            changes.append(name)
    backup = BACKUPS / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + commit[:10])
    backup.mkdir(parents=True, exist_ok=False)
    try:
        manifest = []
        for name in changes:
            target = target_file(name)
            if target.exists():
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
            manifest.append({"path": name, "existed": target.exists()})
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for name in changes:
            target = target_file(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sources[name], target)
    except Exception:
        for entry in reversed(manifest):
            target = target_file(entry["path"])
            saved = backup / entry["path"]
            if entry["existed"] and saved.exists():
                shutil.copy2(saved, target)
            elif not entry["existed"] and target.exists():
                target.unlink()
        raise
    return len(changes), backup

def main():
    global CHAT_ID
    if not TOKEN:
        raise SystemExit("Telegram is not set up yet. See TELEGRAM_SETUP.md.")
    if not CHAT_ID or not CHAT_ID.lstrip("-").isdigit():
        updates = telegram("getUpdates", {"timeout": 0, "limit": 100})
        chats = {str(u["message"]["chat"]["id"]) for u in updates
                 if u.get("message", {}).get("chat", {}).get("type") == "private"
                 and u.get("message", {}).get("text", "").strip().startswith("/start")}
        if len(chats) != 1:
            raise SystemExit("Send /start to your Echo bot, then set ECHO_TELEGRAM_CHAT_ID to the correct numeric chat ID.")
        CHAT_ID = chats.pop()
        print("Found your Telegram private chat ID from /start.", flush=True)
    if not ROOT.exists():
        raise SystemExit("Echo project folder missing.")
    temp, repo, commit = snapshot()
    shutil.rmtree(temp, ignore_errors=True)
    state = {}
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    if state.get("repo") != REPO_URL:
        state = {"repo": REPO_URL, "baseline": commit}
        STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
    try:
        notify("Echo updater connected. Approval required before any GitHub update.")
    except RuntimeError as exc:
        raise SystemExit(str(exc) + " Check your Telegram chat ID.") from None
    offset = 0
    if not shared_bot():  # with a shared bot the chat bridge reads messages
        old_updates = telegram("getUpdates", {"timeout": 0, "limit": 100})
        offset = max((u["update_id"] for u in old_updates), default=0) + 1

    print("Echo approved updater running:", ROOT, flush=True)
    while True:
        temp = None
        try:
            temp, repo, commit = snapshot()
            if commit != state["baseline"]:
                request = commit[:12]
                notify("New Echo update: " + request + "\nReply APPROVE " + request +
                       " to install with backups, or REJECT " + request + " to skip.")
                decision = None
                if shared_bot():
                    # The chat bridge reads your replies and hands them over.
                    DECISION_FILE.unlink(missing_ok=True)
                while decision is None and shared_bot():
                    time.sleep(3)
                    try:
                        answer = DECISION_FILE.read_text(encoding="utf-8").strip()
                    except OSError:
                        continue
                    DECISION_FILE.unlink(missing_ok=True)
                    if answer == "APPROVE " + request:
                        decision = "approve"
                    elif answer == "REJECT " + request:
                        decision = "reject"
                    else:
                        notify("That code doesn't match. Reply APPROVE " + request + " or REJECT " + request + ".")
                while decision is None:
                    for update in telegram("getUpdates", {"offset": offset, "timeout": 25}):
                        offset = max(offset, update["update_id"] + 1)
                        msg = update.get("message", {})
                        if str(msg.get("chat", {}).get("id")) != CHAT_ID:
                            continue
                        answer = msg.get("text", "").strip()
                        if answer == "APPROVE " + request:
                            decision = "approve"
                        elif answer == "REJECT " + request:
                            decision = "reject"
                if decision == "approve":
                    latest = git("ls-remote", REPO_URL, "refs/heads/main").split()[0]
                    if latest != commit:
                        notify("Update changed while awaiting approval. No files installed; will ask again.")
                        continue
                    count, backup = install(repo, commit)
                    notify("Echo copied " + str(count) + " files; backup: " + str(backup) +
                           "\nRestart Echo manually to use updates.")
                else:
                    notify("Echo update rejected; no files changed.")
                state["baseline"] = commit
                STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
            time.sleep(600)
        except KeyboardInterrupt:
            print("Monitor stopped.", flush=True)
            return
        except Exception as exc:
            print("Update check error:", exc, flush=True)
            if isinstance(exc, (TimeoutError, OSError)) and "timed out" in str(exc).lower():
                time.sleep(30)  # brief network blip: retry quietly, no phone alert
                continue
            try:
                notify("Echo updater needs attention: " + str(exc)[:500])
            except Exception:
                pass
            time.sleep(60)
        finally:
            if temp is not None:
                shutil.rmtree(temp, ignore_errors=True)

if __name__ == "__main__":
    main()
