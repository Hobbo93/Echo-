"""Echo Telegram chat bridge (stdlib). Uses a separate Telegram bot from the updater. Text messages use local Ollama.
Voice messages require an optional local speech-to-text engine (whisper CLI);
voice replies require optional local text-to-speech (Piper). No paid API required.
Telegram bots exchange voice notes, not live Telegram voice calls.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from echo_telegram import chat_bot_credentials, _credentials

TOKEN, CHAT_ID = chat_bot_credentials()
HISTORY_TURNS = 8  # remembered back-and-forth exchanges
history = []
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ECHO_MODEL", "llama3.2")
PIPER_MODEL = os.getenv("ECHO_PIPER_MODEL", "").strip()


def telegram(method, params=None):
    url = "https://api.telegram.org/bot" + TOKEN + "/" + method
    try:
        with urllib.request.urlopen(url, data=urllib.parse.urlencode(params or {}).encode(), timeout=45) as r:
            data = json.load(r)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("description", "")
        except ValueError:
            detail = ""
        raise RuntimeError(f"Telegram {method}: HTTP {exc.code} {detail}".strip()) from None
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data["result"]


def send(chat_id, message):
    telegram("sendMessage", {"chat_id": chat_id, "text": message[:4000]})


SYSTEM_PROMPT = ("You are Echo, a practical personal AI assistant. You may discuss plans, "
                 "but cannot claim external actions were performed. Never execute trades, "
                 "publish posts, spend money, or install updates without explicit approval.")


def ask_echo(message):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": message}]
    payload = {"model": MODEL, "messages": messages, "stream": False}
    req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            reply = json.load(r).get("message", {}).get("content", "No response received.")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama error {exc.code}. Is the model pulled? Run: ollama pull {MODEL}") from None
    except urllib.error.URLError:
        raise RuntimeError("Cannot reach Ollama. Make sure the Ollama app is running.") from None
    history.extend([{"role": "user", "content": message},
                    {"role": "assistant", "content": reply}])
    del history[:-HISTORY_TURNS * 2]
    return reply


def transcribe(file_id):
    if not shutil.which("whisper"):
        raise RuntimeError("Voice transcription needs the optional whisper command installed.")
    info = telegram("getFile", {"file_id": file_id})
    url = "https://api.telegram.org/file/bot" + TOKEN + "/" + info["file_path"]
    with tempfile.TemporaryDirectory(prefix="echo_voice_") as folder:
        path = Path(folder) / "voice.ogg"
        with urllib.request.urlopen(url, timeout=60) as r:
            path.write_bytes(r.read(20 * 1024 * 1024 + 1))
        if path.stat().st_size > 20 * 1024 * 1024:
            raise RuntimeError("Voice note too large.")
        subprocess.run(["whisper", str(path), "--model", "base", "--output_dir", folder,
                        "--output_format", "txt"], check=True, timeout=300,
                       capture_output=True)
        return (Path(folder) / "voice.txt").read_text(encoding="utf-8").strip()


def send_voice(chat_id, text):
    if not (shutil.which("piper") and PIPER_MODEL and Path(PIPER_MODEL).is_file()):
        return False
    with tempfile.TemporaryDirectory(prefix="echo_reply_") as folder:
        wav = Path(folder) / "reply.wav"
        subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", str(wav)],
                       input=text, text=True, capture_output=True, check=True, timeout=120)
        # Telegram multipart uploads use the standard library HTTP API.
        boundary = "EchoVoiceBoundary"
        prefix = ('--' + boundary + '\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n'
                  + str(chat_id) + '\r\n--' + boundary +
                  '\r\nContent-Disposition: form-data; name="audio"; filename="reply.wav"\r\n'
                  'Content-Type: audio/wav\r\n\r\n').encode()
        body = prefix + wav.read_bytes() + ('\r\n--' + boundary + '--\r\n').encode()
        req = urllib.request.Request("https://api.telegram.org/bot" + TOKEN + "/sendAudio",
                                     data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.load(r).get("ok", False)


def main():
    if not TOKEN:
        raise SystemExit("Create a second Telegram bot via BotFather and add its token as "
                         "\"chat_bot_token\" in .echo_telegram.json (see TELEGRAM_SETUP.md).")
    if not CHAT_ID or not CHAT_ID.lstrip("-").isdigit():
        raise SystemExit("Add your numeric \"chat_id\" to .echo_telegram.json (see TELEGRAM_SETUP.md).")
    if TOKEN == _credentials()[0]:
        raise SystemExit("Chat and updater cannot share a Telegram bot token. Create a separate chat bot.")
    print("Echo Telegram chat bridge ready. Send a message to your bot.", flush=True)
    updates = telegram("getUpdates", {"timeout": 0, "limit": 100})
    offset = max((u["update_id"] for u in updates), default=-1) + 1
    while True:
        try:
            for update in telegram("getUpdates", {"offset": offset, "timeout": 25}):
                offset = max(offset, update["update_id"] + 1)
                msg = update.get("message") or {}
                chat = msg.get("chat") or {}
                if str(chat.get("id")) != CHAT_ID or chat.get("type") != "private":
                    continue
                text = msg.get("text", "").strip()
                if text.startswith(("APPROVE ", "REJECT ")):
                    send(CHAT_ID, "Update approvals require the dedicated updater. Stop this chat bridge and start the updater to approve an update.")
                    continue
                try:
                    if msg.get("voice"):
                        text = transcribe(msg["voice"]["file_id"])
                    if not text or text.startswith("/start"):
                        send(CHAT_ID, "Echo connected. Send a text or voice note to chat.")
                        continue
                    if text.startswith("/new"):
                        history.clear()
                        send(CHAT_ID, "Started a fresh conversation.")
                        continue
                    reply = ask_echo(text)
                    send(CHAT_ID, reply)
                    send_voice(CHAT_ID, reply[:1200])
                except Exception as exc:
                    send(CHAT_ID, "Echo could not complete that request: " + str(exc)[:250])
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print("Echo Telegram chat error:", exc, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
