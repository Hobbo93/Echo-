"""Telegram notifications for Echo. Keep credentials out of GitHub."""
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"

def _credentials():
    token = os.getenv("ECHO_TELEGRAM_TOKEN", "")
    chat = os.getenv("ECHO_TELEGRAM_CHAT_ID", "")
    if CONFIG.is_file():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8"))
            token = token or str(data.get("bot_token", ""))
            chat = chat or str(data.get("chat_id", ""))
        except (OSError, ValueError):
            pass
    return token, chat

def send_message(message):
    token, chat = _credentials()
    if not token or not chat:
        print("Telegram not configured; see TELEGRAM_SETUP.md")
        return False
    payload = json.dumps({"chat_id": chat, "text": str(message)[:4000]}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return bool(json.load(response).get("ok"))
    except (urllib.error.URLError, ValueError) as exc:
        print("Telegram delivery failed:", type(exc).__name__)
        return False

def send_report(report):
    return send_message("ECHO DAILY REPORT\n\n" + json.dumps(report, indent=2))

def send_alert(problem):
    return send_message("ECHO ALERT\n\n" + str(problem))

def request_approval(task):
    return send_message("ECHO APPROVAL REQUEST\n\n" + str(task) +
        "\n\nThis is a notification only. Approve or reject in Echo's existing approval system.")

if __name__ == "__main__":
    send_message("Echo Telegram notifications are connected.")
