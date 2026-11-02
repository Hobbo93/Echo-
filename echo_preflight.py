"""Echo preflight diagnostics. Run: python echo_preflight.py
Read-only checks: no changes to Echo, no Telegram messages, no trades.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ["echo_server.py", "echo_employees.py", "echo_tasks.py",
           "echo_scheduler.py", "echo_telegram_approved_updater.py",
           "echo_telegram_chat.py", "echo_updater.py"]
def check():
    results = []
    for filename in MODULES:
        path = ROOT / filename
        if not path.exists():
            results.append({"check": filename, "status": "missing"})
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=filename)
            results.append({"check": filename, "status": "ok"})
        except (SyntaxError, UnicodeError) as exc:
            results.append({"check": filename, "status": "error", "detail": str(exc)})
    for name in ("flask",):
        results.append({"check": "dependency:" + name,
                        "status": "ok" if importlib.util.find_spec(name) else "missing"})
    results.append({"check": "telegram_token", "status": "configured" if os.getenv("ECHO_TELEGRAM_TOKEN") else "missing"})
    chat = os.getenv("ECHO_TELEGRAM_CHAT_ID", "").strip()
    results.append({"check": "telegram_chat_id",
                    "status": "configured" if chat.lstrip("-").isdigit() else "missing_or_invalid"})
    updater_token = os.getenv("ECHO_TELEGRAM_TOKEN", "").strip()
    chat_token = os.getenv("ECHO_CHAT_TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("ECHO_CHAT_TELEGRAM_CHAT_ID", "").strip()
    results.append({"check": "chat_bot_token", "status": "configured" if chat_token else "missing"})
    results.append({"check": "chat_bot_chat_id", "status": "configured" if chat_id.lstrip("-").isdigit() else "missing_or_invalid"})
    results.append({"check": "telegram_polling_conflict",
                    "status": "error" if updater_token and chat_token and updater_token == chat_token else "ok",
                    "detail": "Chat and updater must use different Telegram bot tokens."})
    return results

if __name__ == "__main__":
    results = check()
    print(json.dumps(results, indent=2))
    errors = [x for x in results if x["status"] == "error"]
    raise SystemExit(1 if errors else 0)
