"""Telegram notifications for Echo. Keep credentials out of GitHub."""
import os
import json
import urllib.request
import urllib.error
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"
# When Echo chats through the same bot as the updater, the chat bridge
# receives APPROVE/REJECT replies and passes them on through this file.
DECISION_FILE = Path.home() / ".echo_update_decision"

REPORT_LABELS = [
    ("queued_tasks", "Tasks queued today"),
    ("pending_approval", "Waiting for approval"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("business_research_target", "Business research target"),
    ("top_leads_target", "Top leads target"),
    ("ai_video_target", "AI video target"),
    ("edited_clip_target", "Edited clip target"),
]


def _credentials():
    token = os.getenv("ECHO_TELEGRAM_TOKEN", "").strip()
    chat = os.getenv("ECHO_TELEGRAM_CHAT_ID", "").strip()
    if CONFIG.is_file():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            token = token or str(data.get("bot_token", "")).strip()
            chat = chat or str(data.get("chat_id", "")).strip()
        except (OSError, ValueError, AttributeError):
            pass
    return token, chat


def chat_bot_credentials():
    """Token and chat ID for the separate Telegram chat bot.

    Env vars win; otherwise "chat_bot_token" in ~/.echo_telegram.json.
    With no separate chat bot, Echo chats through the main bot.
    A private chat ID is your Telegram user ID, so it is the same for every
    bot and falls back to the main "chat_id".
    """
    token = os.getenv("ECHO_CHAT_TELEGRAM_TOKEN", "").strip()
    chat = os.getenv("ECHO_CHAT_TELEGRAM_CHAT_ID", "").strip()
    if CONFIG.is_file():
        try:
            data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            token = token or str(data.get("chat_bot_token", "")).strip()
        except (OSError, ValueError, AttributeError):
            pass
    main_token, main_chat = _credentials()
    return token or main_token, chat or main_chat


def shared_bot():
    """True when chat and update approvals use the same Telegram bot."""
    return chat_bot_credentials()[0] == _credentials()[0]


def is_configured():
    """True when a token and numeric chat ID are available. Sends nothing."""
    token, chat = _credentials()
    return bool(token) and chat.lstrip("-").isdigit()


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
    except (OSError, ValueError) as exc:  # URLError, HTTPError and timeouts are OSErrors
        print("Telegram delivery failed:", type(exc).__name__)
        return False


def format_report(report):
    """Turn a scheduler report into a short, phone-friendly message."""
    title = "ECHO REPORT"
    if report.get("report_time"):
        title += " " + report["report_time"]
    lines = [title + " - " + str(report.get("date", "")), ""]
    for key, label in REPORT_LABELS:
        if key in report:
            lines.append(label + ": " + str(report[key]))
    if report.get("note"):
        lines += ["", report["note"]]
    return "\n".join(lines)


def send_report(report):
    return send_message(format_report(report))


def send_alert(problem):
    return send_message("ECHO ALERT\n\n" + str(problem))


def request_approval(task):
    return send_message("ECHO APPROVAL REQUEST\n\n" + str(task) +
        "\n\nThis is a notification only. Approve or reject in Echo's existing approval system.")


if __name__ == "__main__":
    send_message("Echo Telegram notifications are connected.")
