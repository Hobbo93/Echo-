"""Echo approval-gated GitHub updater. Standard library only.
Start with: python echo_telegram_approved_updater.py
Set ECHO_TELEGRAM_TOKEN and ECHO_TELEGRAM_CHAT_ID in the environment.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

REPO_URL = "https://github.com/Hobbo93/Echo-.git"
ROOT = Path(__file__).resolve().parent
TOKEN = os.environ.get("ECHO_TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("ECHO_TELEGRAM_CHAT_ID", "").strip()
STATE_FILE = Path.home() / ".echo_approved_update_state.json"
BACKUPS = Path.home() / "Echo_update_backups"
IGNORED = {".git", ".env", "venv", ".venv", "__pycache__", "node_modules"}

def telegram(method, params):
    url = "https://api.telegram.org/bot" + TOKEN + "/" + method
    body = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=body, timeout=40) as response:
        data = json.load(response)
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
    if not TOKEN or not CHAT_ID:
        raise SystemExit("Set ECHO_TELEGRAM_TOKEN and ECHO_TELEGRAM_CHAT_ID first.")
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
    old_updates = telegram("getUpdates", {"timeout": 0, "limit": 100})
    offset = max((u["update_id"] for u in old_updates), default=0) + 1
    notify("Echo approved updater connected to Hobbo93/Echo-. Monitoring main every 10 minutes. No changes without approval.")
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
