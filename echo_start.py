"""Start every part of Echo that is set up, each in its own window.
Run: py echo_start.py   (or double-click start_echo.bat)
"""
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from echo_preflight import check_ollama
from echo_telegram import is_configured, chat_bot_credentials
import echo_phone

ROOT = Path(__file__).resolve().parent


def launch(title, script):
    if sys.platform == "win32":
        # A string (not a list) so the new cmd window sees "&" itself;
        # /k keeps the window open so any error stays readable.
        command = f'cmd /k title {title} & "{sys.executable}" echo_keepalive.py {script}'
        subprocess.Popen(command, cwd=ROOT,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen([sys.executable, "echo_keepalive.py", script], cwd=ROOT)
    print("Started:", title)


STARTUP_BAT = """@echo off
rem Starts Echo when Windows starts. Written by echo_start.py, which keeps the folder below up to date.
cd /d "{root}"
timeout /t 30 /nobreak >nul
py -m pip install -q -r requirements.txt
py echo_start.py --no-browser
"""


def startup_folder():
    appdata = os.getenv("APPDATA")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" if appdata else None


def install_autostart(folder=None):
    """Make Echo start with Windows, from THIS folder. Older Echo start-up files that point somewhere
    else are switched off (renamed to .old, not deleted). Returns a short message, or '' if unchanged."""
    folder = Path(folder) if folder else startup_folder()
    if not folder or not folder.is_dir():
        return ""
    ours = folder / "Echo.bat"
    want = STARTUP_BAT.format(root=ROOT).replace("\n", "\r\n")
    changed = []
    for f in folder.glob("*.bat"):
        if f == ours:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "echo_start.py" in text:
            f.replace(f.with_name(f.name + ".old"))
            changed.append(f"switched off an old start-up file ({f.name})")
    try:
        current = ours.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current.replace("\r\n", "\n") != want.replace("\r\n", "\n"):
        ours.write_bytes(want.encode("utf-8"))
        changed.append(f"Echo will now start with Windows from {ROOT}")
    return "; ".join(changed)


def already_running():
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/health", timeout=3):
            return True
    except Exception:
        return False


def main():
    if sys.platform == "win32":
        try:
            note = install_autostart()
            if note:
                print("Start-up:", note)
        except Exception as exc:
            print("Couldn't set Echo to start with Windows:", exc)
    if already_running():
        print("Echo is already running. Close its windows first if you want to restart it.")
        if "--no-browser" not in sys.argv:
            webbrowser.open("http://127.0.0.1:5000")
        return
    ollama = check_ollama()
    if ollama["status"] != "ok":
        print("Warning:", ollama["detail"])

    launch("Echo Server", "echo_server.py")
    launch("Echo Scheduler", "echo_scheduler.py")

    if is_configured():
        launch("Echo Updater", "echo_telegram_approved_updater.py")
    else:
        print("Skipped Telegram reports + updater: run setup_echo.bat to add Telegram.")

    token, chat = chat_bot_credentials()
    if token and chat.lstrip("-").isdigit():
        launch("Echo Telegram Chat", "echo_telegram_chat.py")
    else:
        print("Skipped Telegram chat: add a second bot token in setup_echo.bat to enable it.")

    if echo_phone.is_configured():
        launch("Echo Phone", "echo_phone.py")
    else:
        print("Skipped phone calls: see PHONE_SETUP.md to let Echo ring you.")

    time.sleep(3)
    if "--no-browser" not in sys.argv:
        webbrowser.open("http://127.0.0.1:5000")
    print("\nEcho HQ is open in your browser: http://127.0.0.1:5000")
    print("Close an Echo window to stop that part.")


if __name__ == "__main__":
    main()
