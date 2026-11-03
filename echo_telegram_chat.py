"""Echo Telegram chat bridge. Uses your Echo bot (or a separate chat bot if set).
Text and voice notes go to local Ollama. Send a voice note and Echo answers
with a voice note too (see echo_voice.py). No paid API required.
Telegram bots can't take live calls; /callme rings your phone if Echo's
phone line is set up (see PHONE_SETUP.md).
"""
import json
import os
import tempfile
import threading
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from echo_telegram import (chat_bot_credentials, shared_bot, yes_no, DECISION_FILE,
                           PENDING_FILE, NO_KEYBOARD)

TOKEN, CHAT_ID = chat_bot_credentials()
HISTORY_TURNS = 8  # remembered back-and-forth exchanges
history = []
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ECHO_MODEL", "llama3.2")

import echo_voice
import echo_photos
import echo_roblox
import echo_leads
import echo_trading


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


def send(chat_id, message, keyboard=None):
    params = {"chat_id": chat_id, "text": message[:4000]}
    if keyboard:
        params["reply_markup"] = keyboard
    telegram("sendMessage", params)


SYSTEM_PROMPT = ("You are Echo, a practical personal AI assistant. You may discuss plans, "
                 "but cannot claim external actions were performed. Never execute trades, "
                 "publish posts, spend money, or install updates without explicit approval.")


VOICE_STYLE = (" The user sent a voice note and will hear your reply spoken aloud: answer "
               "like a friend on the phone, in one to four short natural sentences, "
               "with no lists, headings, emojis or markdown.")


def ask_echo(message, spoken=False):
    system = SYSTEM_PROMPT + (VOICE_STYLE if spoken else "")
    messages = [{"role": "system", "content": system}, *history,
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
    info = telegram("getFile", {"file_id": file_id})
    url = "https://api.telegram.org/file/bot" + TOKEN + "/" + info["file_path"]
    with tempfile.TemporaryDirectory(prefix="echo_voice_") as folder:
        path = Path(folder) / "voice.ogg"
        with urllib.request.urlopen(url, timeout=60) as r:
            path.write_bytes(r.read(20 * 1024 * 1024 + 1))
        if path.stat().st_size > 20 * 1024 * 1024:
            raise RuntimeError("Voice note too large.")
        return echo_voice.transcribe(path)


def _upload(method, field, chat_id, path, content_type, caption=""):
    """Send a file to Telegram (multipart upload, standard library only)."""
    boundary = "EchoVoiceBoundary7d93"
    extra = ""
    if caption:
        extra = ("\r\n--" + boundary + '\r\nContent-Disposition: form-data; name="caption"\r\n\r\n'
                 + caption[:1000])
    body = ("--" + boundary + '\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n'
            + str(chat_id) + extra + "\r\n--" + boundary
            + '\r\nContent-Disposition: form-data; name="' + field + '"; filename="' + path.name + '"\r\n'
            + "Content-Type: " + content_type + "\r\n\r\n").encode() + path.read_bytes() \
        + ("\r\n--" + boundary + "--\r\n").encode()
    req = urllib.request.Request("https://api.telegram.org/bot" + TOKEN + "/" + method, data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r).get("ok", False)


def send_voice(chat_id, text):
    """Reply with a spoken voice note. Returns False if no voice is available."""
    with tempfile.TemporaryDirectory(prefix="echo_reply_") as folder:
        path, is_voice_note = echo_voice.speak_to_file(text, folder)
        if not path:
            return False
        if is_voice_note:
            return _upload("sendVoice", "voice", chat_id, path, "audio/ogg")
        return _upload("sendAudio", "audio", chat_id, path, "audio/wav")


def download(file_id, limit=20 * 1024 * 1024):
    info = telegram("getFile", {"file_id": file_id})
    url = "https://api.telegram.org/file/bot" + TOKEN + "/" + info["file_path"]
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("That file is too large.")
    return data


def send_photo(chat_id, path, caption=""):
    kind = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    if path.stat().st_size > 9 * 1024 * 1024 or path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
        return _upload("sendDocument", "document", chat_id, path, "application/octet-stream", caption)
    return _upload("sendPhoto", "photo", chat_id, path, kind, caption)


last_photo = {}  # the most recent photo you sent, so you can ask follow-up questions


def handle_photo(msg):
    """You sent a photo: save it and have Echo look at it."""
    if msg.get("photo"):
        file_id = msg["photo"][-1]["file_id"]  # largest size
    else:
        file_id = msg["document"]["file_id"]
    data = download(file_id)
    path = echo_photos.save_photo(data, "from_you")
    last_photo.update(data=data, path=path, time=time.time())
    question = (msg.get("caption") or "").strip()
    if not echo_photos.has_vision():
        send(CHAT_ID, "Saved your photo as " + path.name + ".\n\n" + echo_photos.need_vision_message())
        return
    telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
    reply = echo_photos.look([data], question)
    history.extend([{"role": "user", "content": "[sent a photo] " + question},
                    {"role": "assistant", "content": reply}])
    del history[:-HISTORY_TURNS * 2]
    send(CHAT_ID, reply)


def handle_command(text):
    """Photo and approval commands. Returns True if the message was handled."""
    lower = text.lower().strip()
    if PENDING_FILE.exists() and shared:
        choice = yes_no(text)
        if choice:
            DECISION_FILE.write_text(choice, encoding="utf-8")
            send(CHAT_ID, "Installing the update…" if choice == "yes" else "OK, skipping that update.",
                 NO_KEYBOARD)
            return True
    if lower.startswith(("approve ", "reject ")):
        if shared and PENDING_FILE.exists():
            DECISION_FILE.write_text("yes" if lower.startswith("approve") else "no", encoding="utf-8")
            send(CHAT_ID, "Got it.", NO_KEYBOARD)
        else:
            send(CHAT_ID, "There's no update waiting right now.")
        return True
    if lower.startswith("/getvision"):
        if echo_photos.has_vision():
            send(CHAT_ID, "I can already see photos. Send me one!")
            return True
        send(CHAT_ID, "Downloading " + echo_photos.VISION_MODEL + " (" + echo_photos.VISION_SIZE +
             "). I'll tell you when it's ready.")
        def pull():  # in the background so you can keep chatting
            try:
                echo_photos.pull_vision(lambda pct, status: send(CHAT_ID, "Download " + str(pct) + "%"))
                send(CHAT_ID, "Done! I can see photos now. Send me one, and add a caption to ask about it.")
            except Exception as exc:
                send(CHAT_ID, "The download didn't finish: " + str(exc)[:200])
        threading.Thread(target=pull, daemon=True).start()
        return True
    if lower.startswith("/screenshot") or echo_photos.SCREENSHOT_WORDS.search(text):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "upload_photo"})
        path = echo_photos.screenshot()
        send_photo(CHAT_ID, path, "Your PC screen right now")
        return True
    if lower.startswith("/photos"):
        photos = echo_photos.list_photos(10)
        if not photos:
            send(CHAT_ID, "No photos saved yet. Send me one, or /screenshot.")
        else:
            send(CHAT_ID, "Your latest photos:\n" + "\n".join(
                str(n) + ". " + p.name for n, p in enumerate(photos, 1)) +
                "\n\nSend /photo 1 (or part of a name) to get one.")
        return True
    if lower.startswith("/photo"):
        query = text.split(None, 1)[1] if len(text.split()) > 1 else "1"
        path = echo_photos.find_photo(query)
        if not path:
            send(CHAT_ID, "I couldn't find that photo. Send /photos to see the list.")
        else:
            telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "upload_photo"})
            send_photo(CHAT_ID, path, path.name)
        return True
    if lower.startswith("/roblox") or ("roblox" in lower and echo_roblox.looks_like_build_request(text)):
        request = text.split(None, 1)[1] if lower.startswith("/roblox") and len(text.split()) > 1 else text
        if lower.strip() == "/roblox":
            send(CHAT_ID, "Tell me what to build, e.g. /roblox a snowy obby with 20 stages, "
                          "/roblox a big night city, /roblox a desert battle arena.")
            return True
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        send(CHAT_ID, echo_roblox.describe(echo_roblox.build(request)))
        return True
    if "place trade" in lower or "skip trade" in lower or (
            echo_trading.pending() and not PENDING_FILE.exists() and yes_no(text)):
        if "skip" in lower or yes_no(text) == "no":
            send(CHAT_ID, echo_trading.skip(), NO_KEYBOARD)
            return True
        send(CHAT_ID, "Placing the trade…", NO_KEYBOARD)

        def place():
            try:
                msg, png = echo_trading.approve()
                if png:
                    path = Path(tempfile.gettempdir()) / "echo_trade.png"
                    path.write_bytes(png)
                    _upload("sendPhoto", "photo", CHAT_ID, path, "image/png", "Your trade: blue = entry, "
                            "red = stop-loss, green = target")
                send(CHAT_ID, msg)
            except Exception as exc:
                send(CHAT_ID, "The trade was NOT placed: " + str(exc)[:300])
        threading.Thread(target=place, daemon=True).start()
        return True
    if lower.startswith("/trade propose") or lower.startswith("/trade idea"):
        send(CHAT_ID, "Scanning the watchlist for the best setup…")
        threading.Thread(target=lambda: _safe(echo_trading.send_idea_to_phone), daemon=True).start()
        return True
    if lower.startswith("/trade") or lower.startswith("paper "):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        send(CHAT_ID, echo_trading.handle(text) or echo_trading.handle("/trade"))
        return True
    if lower.startswith(("/leads", "/findleads")):
        fresh = lower.startswith("/findleads") or "new" in lower
        result = None if fresh else echo_leads.latest()
        if result:
            send(CHAT_ID, echo_leads.summary(result))
            return True
        if not echo_leads.API_KEY:
            send(CHAT_ID, "I need a Google Places API key to find businesses. Run setup_echo.bat on "
                          "your PC and paste it in (LEADS_SETUP.md shows how to get one).")
            return True
        send(CHAT_ID, "Finding 20 new local businesses, with phones, emails and photos. "
                      "This takes a few minutes; I'll message you the list.")

        def run():
            try:
                send(CHAT_ID, echo_leads.summary(echo_leads.research_leads()))
            except Exception as exc:
                send(CHAT_ID, "Lead research didn't finish: " + str(exc)[:300])
        threading.Thread(target=run, daemon=True).start()
        return True
    if lower.startswith("/maps"):
        maps = echo_roblox.list_maps(10)
        send(CHAT_ID, "Your Roblox maps:\n" + "\n".join(m.name for m in maps) if maps
             else "No Roblox maps yet. Try /roblox a fun obby")
        return True
    if lower.startswith(("/help", "/start")):
        send(CHAT_ID, "Echo here. You can:\n"
             "• text me or send a voice note\n"
             "• send a photo (add a caption to ask about it)\n"
             "• /screenshot - photo of your PC screen\n"
             "• /photos and /photo 1 - get saved photos back\n"
             "• /roblox a snowy obby - build a Roblox map (/maps lists them)\n"
             "• /leads - today's 20 businesses (/findleads gets new ones)\n"
             "• /trade analyse BHP.AX - chart read + risk plan\n"
             "• /trade propose - best trade idea with a chart; tap Place trade to approve\n"
             "• /callme - I ring your phone\n"
             "• /new - start a fresh chat")
        return True
    return False


shared = False


def _safe(fn):
    try:
        fn()
    except Exception as exc:
        send(CHAT_ID, "Echo trading desk problem: " + str(exc)[:300])


def main():
    global shared
    if not TOKEN:
        raise SystemExit("Telegram is not set up yet. Run setup_echo.bat (see TELEGRAM_SETUP.md).")
    if not CHAT_ID or not CHAT_ID.lstrip("-").isdigit():
        raise SystemExit("Add your numeric \"chat_id\" to .echo_telegram.json (see TELEGRAM_SETUP.md).")
    shared = shared_bot()
    print("Echo Telegram chat bridge ready. Send a message to your bot.", flush=True)
    while True:  # another Echo window may still be closing; keep trying
        try:
            updates = telegram("getUpdates", {"timeout": 0, "limit": 100})
            break
        except Exception as exc:
            print("Waiting for Telegram:", str(exc)[:150], flush=True)
            time.sleep(10)
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
                doc = msg.get("document") or {}
                is_photo = bool(msg.get("photo")) or str(doc.get("mime_type", "")).startswith("image/")
                try:
                    if is_photo:
                        handle_photo(msg)
                        continue
                    if text and handle_command(text):
                        continue
                    # A follow-up question about the photo you just sent
                    if text and last_photo and time.time() - last_photo["time"] < 180 \
                            and echo_photos.has_vision() and not text.startswith("/"):
                        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
                        send(CHAT_ID, echo_photos.look([last_photo["data"]], text, history[-6:]))
                        continue
                    spoken = bool(msg.get("voice"))
                    if spoken:
                        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
                        text = transcribe(msg["voice"]["file_id"])
                        if not text:
                            send(CHAT_ID, "Sorry, I couldn't hear anything in that voice note.")
                            continue
                    if not text:
                        continue
                    if text.startswith("/callme"):
                        import echo_phone
                        send(CHAT_ID, echo_phone.call_me("Hi, it's Echo. You asked me to call. What's up?"))
                        continue
                    if text.startswith("/new"):
                        history.clear()
                        last_photo.clear()
                        send(CHAT_ID, "Started a fresh conversation.")
                        continue
                    telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
                    reply = ask_echo(text, spoken)
                    if spoken:
                        send(CHAT_ID, "🎙️ " + text + "\n\n" + reply)
                        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "record_voice"})
                        send_voice(CHAT_ID, reply[:1500])
                    else:
                        send(CHAT_ID, reply)
                except Exception as exc:
                    send(CHAT_ID, "Echo could not complete that request: " + str(exc)[:250])
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print("Echo Telegram chat error:", exc, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
