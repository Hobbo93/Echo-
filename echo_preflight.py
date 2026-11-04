"""Echo preflight diagnostics. Run: python echo_preflight.py
Read-only checks: no changes to Echo, no Telegram messages, no trades.
"""
import ast
import importlib.util
import json
import shutil
import urllib.request
from pathlib import Path
import echo_brain

ROOT = Path(__file__).resolve().parent
MODULES = ["echo_server.py", "echo_employees.py", "echo_tasks.py",
           "echo_scheduler.py", "echo_telegram_approved_updater.py",
           "echo_telegram_chat.py", "echo_updater.py", "echo_telegram.py",
           "echo_content.py", "echo_automation.py",
           "echo_leads.py", "echo_memory.py",
           "echo_setup.py", "echo_start.py", "echo_voice.py", "echo_phone.py"]
def check_ollama():
    """Is Ollama running, and is Echo's model pulled?"""
    model = echo_brain.model()
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=5) as response:
            names = [m.get("name", "") for m in json.load(response).get("models", [])]
    except Exception:
        return {"check": "ollama", "status": "error",
                "detail": "Ollama is not running. Start the Ollama app, then try again."}
    if not any(name == model or name.startswith(model + ":") for name in names):
        return {"check": "ollama", "status": "error",
                "detail": "Model missing. Run: ollama pull " + model}
    return {"check": "ollama", "status": "ok", "detail": model}


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
                        "status": "ok" if importlib.util.find_spec(name) else "missing",
                        "detail": "Install with: py -m pip install -r requirements.txt"})
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Australia/Adelaide")
        results.append({"check": "timezone_data", "status": "ok"})
    except Exception:
        # Windows has no built-in timezone data; Echo needs the tzdata package.
        results.append({"check": "timezone_data", "status": "error",
                        "detail": "Install with: py -m pip install -r requirements.txt"})
    results.append(check_ollama())
    try:
        from echo_leads import API_KEY as places_key
    except Exception:
        places_key = ""
    results.append({"check": "google_places_key",
                    "status": "configured" if places_key else "missing",
                    "detail": "Only needed for echo_leads.py business research."})
    # Notifications accept env vars or ~/.echo_telegram.json (see TELEGRAM_SETUP.md).
    # The approval updater only reads env vars, so it is checked separately.
    try:
        from echo_telegram import is_configured
        notify_ok = is_configured()
    except Exception:
        notify_ok = False
    results.append({"check": "telegram_notifications",
                    "status": "configured" if notify_ok else "missing"})
    try:
        from echo_telegram import _credentials, chat_bot_credentials
        updater_token, chat = _credentials()
        chat_token, chat_id = chat_bot_credentials()
    except Exception:
        updater_token = chat = chat_token = chat_id = ""
    results.append({"check": "telegram_token", "status": "configured" if updater_token else "missing"})
    results.append({"check": "telegram_chat_id",
                    "status": "configured" if chat.lstrip("-").isdigit() else "missing_or_invalid"})
    results.append({"check": "ffmpeg", "status": "ok" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "missing",
                    "detail": "Only needed for echo_content.py video clips."})
    results.append({"check": "chat_bot_token", "status": "configured" if chat_token else "missing"})
    results.append({"check": "chat_bot_chat_id", "status": "configured" if chat_id.lstrip("-").isdigit() else "missing_or_invalid"})
    results.append({"check": "telegram_polling_conflict",
                    "status": "error" if updater_token and chat_token and updater_token == chat_token else "ok",
                    "detail": "Chat and updater must use different Telegram bot tokens."})
    try:
        import echo_voice
        voice_in, voice_out = echo_voice.can_transcribe(), echo_voice.can_speak()
    except Exception:
        voice_in = voice_out = False
    results.append({"check": "voice_notes_in", "status": "ok" if voice_in else "missing",
                    "detail": "Optional. setup_echo.bat -> Y for voice notes."})
    results.append({"check": "voice_notes_out", "status": "ok" if voice_out else "missing",
                    "detail": "Optional. Uses the Windows voice."})
    try:
        import echo_phone
        phone = echo_phone.is_configured()
    except Exception:
        phone = False
    results.append({"check": "phone_calls", "status": "configured" if phone else "missing",
                    "detail": "Optional. See PHONE_SETUP.md."})
    if phone:
        results.append({"check": "cloudflared", "status": "ok" if shutil.which("cloudflared") else "error",
                        "detail": "Needed for phone calls. setup_echo.bat -> Y for the tunnel."})
    return results

if __name__ == "__main__":
    results = check()
    print(json.dumps(results, indent=2))
    errors = [x for x in results if x["status"] == "error"]
    raise SystemExit(1 if errors else 0)
