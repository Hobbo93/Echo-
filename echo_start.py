"""Start every part of Echo that is set up, each in its own window.
Run: py echo_start.py   (or double-click start_echo.bat)
"""
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from echo_preflight import check_ollama
from echo_telegram import is_configured, chat_bot_credentials

ROOT = Path(__file__).resolve().parent


def launch(title, script):
    if sys.platform == "win32":
        # A string (not a list) so the new cmd window sees "&" itself;
        # /k keeps the window open so any error stays readable.
        command = f'cmd /k title {title} & "{sys.executable}" {script}'
        subprocess.Popen(command, cwd=ROOT,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen([sys.executable, script], cwd=ROOT)
    print("Started:", title)


def main():
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

    time.sleep(3)
    webbrowser.open("http://127.0.0.1:5000")
    print("\nEcho HQ is open in your browser: http://127.0.0.1:5000")
    print("Close an Echo window to stop that part.")


if __name__ == "__main__":
    main()
