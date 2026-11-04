"""Echo Telegram chat bridge. Uses your Echo bot (or a separate chat bot if set).
Text and voice notes go to local Ollama. Send a voice note and Echo answers
with a voice note too (see echo_voice.py). No paid API required.
Telegram bots can't take live calls; /callme rings your phone if Echo's
phone line is set up (see PHONE_SETUP.md).
"""
import json
import re
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

import echo_voice
import echo_photos
import echo_roblox
import echo_leads
import echo_trading
import echo_shopify
import echo_email
import echo_connections
import echo_personality
import echo_business
import echo_memory
import echo_growth
import echo_opusclip
import echo_router
import echo_computer
import echo_guide
import echo_tradeshot
import echo_brain
import echo_log
import echo_backup
import echo_health
import echo_ceo


def telegram(method, params=None):
    url = "https://api.telegram.org/bot" + TOKEN + "/" + method
    tries = 1 if method == "getUpdates" else 4  # retry sends through brief internet drops
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, data=urllib.parse.urlencode(params or {}).encode(), timeout=45) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as exc:
            try:
                detail = json.load(exc).get("description", "")
            except ValueError:
                detail = ""
            raise RuntimeError(f"Telegram {method}: HTTP {exc.code} {detail}".strip()) from None
        except (urllib.error.URLError, OSError):
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
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
    echo_personality.feel(message)
    system = echo_personality.persona(spoken, message)
    if not history:  # fresh start (or Echo restarted): pick up where the last chat left off
        earlier = echo_memory.last_summary("telegram")
        if earlier:
            system += "\n\nSummary of your last conversation:\n" + earlier
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": message}]
    echo_brain.mark_active()
    payload = {"model": echo_brain.model(), "messages": messages, "stream": False,
               "keep_alive": echo_brain.KEEP_ALIVE}
    req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            reply = json.load(r).get("message", {}).get("content", "No response received.")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama error {exc.code}. Is the model pulled? Run: ollama pull {echo_brain.model()}") from None
    except urllib.error.URLError:
        raise RuntimeError("Cannot reach Ollama. Make sure the Ollama app is running.") from None
    reply = echo_growth.check_reply(reply)
    echo_growth.after_reply(message, reply)
    history.extend([{"role": "user", "content": message},
                    {"role": "assistant", "content": reply}])
    del history[:-HISTORY_TURNS * 2]
    try:
        echo_memory.log_turn("telegram", message, reply)
    except Exception:
        pass  # memory problems must never stop a reply
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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r).get("ok", False)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, OSError):
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))


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
    if question and re.search(r"\b(shopify|store|shop|listing|product)\b", question, re.I):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        reply = echo_shopify.handle(question, images=[path], force=True)
        if reply and "sent this to your phone" not in reply:
            send(CHAT_ID, reply)
        return
    if echo_tradeshot.wants_trade_read(question):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        reply, png = echo_tradeshot.analyse_screenshot(data, question)
        if png:
            chart = Path(tempfile.gettempdir()) / "echo_trade_read.png"
            chart.write_bytes(png)
            try:
                _upload("sendPhoto", "photo", CHAT_ID, chart, "image/png", "Echo's plan: blue = entry, red = stop-loss, green = target")
            except Exception:
                pass
        send(CHAT_ID, reply)
        return
    if not echo_photos.has_vision():
        send(CHAT_ID, "Saved your photo as " + path.name + ".\n\n" + echo_photos.need_vision_message())
        return
    telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
    reply = echo_photos.look([data], question)
    history.extend([{"role": "user", "content": "[sent a photo] " + question},
                    {"role": "assistant", "content": reply}])
    del history[:-HISTORY_TURNS * 2]
    send(CHAT_ID, reply)


def _safe_text(fn, *args, **kwargs):
    """Run a tool and turn any crash into an honest message instead of silence."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        echo_log.error(getattr(fn, "__name__", "telegram"), exc)
        return "That didn't work: " + str(exc)[:300]


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
    # Trading stop button comes first, so it always works.
    if (echo_trading.STOP_RE.match(text) or echo_trading.RESUME_RE.match(text)
            or echo_trading.SELL_ALL_RE.match(text)):
        reply = _safe_text(echo_trading.handle, text)
        sell_all = (echo_trading.pending() or {}).get("side") == "sell_all"
        send(CHAT_ID, reply, echo_trading.TRADE_KEYBOARD if sell_all else None)
        return True
    if echo_email.pending() and yes_no(text) and not echo_shopify.pending() and not echo_trading.pending():
        if yes_no(text) == "no":
            send(CHAT_ID, echo_email.skip(), NO_KEYBOARD)
            return True
        try:
            send(CHAT_ID, echo_email.approve(), NO_KEYBOARD)
        except Exception as exc:
            send(CHAT_ID, "The email was NOT sent: " + str(exc)[:300], NO_KEYBOARD)
        return True
    if echo_guide.wants_stop(text):
        send(CHAT_ID, echo_guide.stop())
        return True
    if echo_guide.is_start(text) or echo_guide.wants_next(text):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "upload_photo"})
        starting = echo_guide.is_start(text)

        def guide():
            tip, shot = echo_guide.start(text) if starting else echo_guide.step()
            if shot:
                try:
                    send_photo(CHAT_ID, shot, tip[:1000])
                    return
                except Exception:
                    pass
            send(CHAT_ID, tip)
        threading.Thread(target=guide, daemon=True).start()
        return True
    pc = echo_computer.plan(text)
    if pc:
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "upload_photo"})

        def on_pc():
            msg, shot = echo_computer.do(pc)
            if shot:
                try:
                    send_photo(CHAT_ID, shot, msg)
                    return
                except Exception as exc:
                    msg += f" (Couldn't send the screenshot: {str(exc)[:100]})"
            send(CHAT_ID, msg)
        threading.Thread(target=on_pc, daemon=True).start()
        return True
    routed = echo_router.route(text)
    if routed and routed[0] == "connections":
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        threading.Thread(target=lambda: send(CHAT_ID, _safe_text(echo_router.answer_connections, text)),
                         daemon=True).start()
        return True
    if routed and routed[0] in ("opus", "email"):
        text = routed[1]
        lower = text.lower()
    if routed and routed[0] == "shopify":
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})

        def store_request():
            reply = _safe_text(echo_shopify.handle, text, force=True)
            if reply and "sent this to your phone" not in reply:
                send(CHAT_ID, reply)
        threading.Thread(target=store_request, daemon=True).start()
        return True
    if echo_email.EMAIL_RE.match(text):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})

        def mail():
            reply = echo_email.handle(text)
            if reply and "Sent to your phone" not in reply:
                send(CHAT_ID, reply)
        threading.Thread(target=mail, daemon=True).start()
        return True
    if (echo_opusclip.pending() and yes_no(text) and not echo_shopify.pending()
            and not echo_trading.pending() and not echo_email.pending()):
        if yes_no(text) == "no":
            send(CHAT_ID, echo_opusclip.skip(), NO_KEYBOARD)
            return True
        send(CHAT_ID, "On it…", NO_KEYBOARD)

        def do_opus():
            try:
                send(CHAT_ID, echo_opusclip.approve())
            except Exception as exc:
                send(CHAT_ID, "That did NOT go through: " + str(exc)[:300])
        threading.Thread(target=do_opus, daemon=True).start()
        return True
    if re.match(r"^/(clips?|post|opus)\b", lower):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})

        def opus():
            try:
                reply = echo_opusclip.handle(text)
            except Exception as exc:
                reply = "OpusClip problem: " + str(exc)[:300]
            if reply and "sent it to your phone" not in reply:
                send(CHAT_ID, reply)
        threading.Thread(target=opus, daemon=True).start()
        return True
    if echo_shopify.pending() and yes_no(text) and not echo_trading.pending():
        if yes_no(text) == "no":
            send(CHAT_ID, echo_shopify.skip(), NO_KEYBOARD)
            return True
        send(CHAT_ID, "On it, updating the store…", NO_KEYBOARD)

        def do_store():
            try:
                send(CHAT_ID, echo_shopify.approve())
            except Exception as exc:
                send(CHAT_ID, "The store change did NOT go through: " + str(exc)[:300])
        threading.Thread(target=do_store, daemon=True).start()
        return True
    if lower.startswith("/connections") or re.search(r"\bwhat(?:'s| is) connected\b|\bconnections?\b.*\b(status|check)\b", lower):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        send(CHAT_ID, echo_connections.summary())
        return True
    if lower.startswith(("/shop", "/products", "/orders")) or (
            re.search(r"\b(shopify|my store|the store|furventure)\b", lower) and echo_shopify.STORE_WORDS.search(lower)):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        q = "orders" if lower.startswith("/orders") else text

        def store():
            reply = echo_shopify.handle(q, force=True)
            if reply and "sent this to your phone" not in reply:
                send(CHAT_ID, reply)
        threading.Thread(target=store, daemon=True).start()
        return True
    if lower.startswith(("approve ", "reject ")):
        if shared and PENDING_FILE.exists():
            DECISION_FILE.write_text("yes" if lower.startswith("approve") else "no", encoding="utf-8")
            send(CHAT_ID, "Got it.", NO_KEYBOARD)
        else:
            send(CHAT_ID, "There's no update waiting right now.")
        return True
    cmd = {"/pipeline": "pipeline", "/money": "money", "/ceo": "summary", "/summary": "summary",
           "/status": "status", "/records": "records", "/tickets": "tickets", "/goals": "goals",
           "/followups": "follow ups", "/subscriptions": "subscriptions"}.get(lower.split()[0] if lower else "")
    office = echo_business.handle(None, cmd or text) if (cmd or re.match(
        r"^(pipeline|pitch |mark .+ (new|contacted|follow ?up|meeting|won|lost)$|follow ?ups|income |expense |"
        r"subscription |subscriptions|enquiry .+:|tickets|reply #?\d|close #?\d|my goal is|goals$|status$|records$)", lower)) else None
    if office:
        if cmd == "summary" or lower.startswith("pitch") or lower.startswith("reply"):
            telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        send(CHAT_ID, office)
        return True
    if lower.startswith("/brain") or re.search(r"\b(upgrade|improve) (your|echo'?s?) brain\b|\b(bigger|smarter) (ai )?model\b", lower):
        cmd = text if lower.startswith("/brain") else ("/brain upgrade" if "upgrade" in lower else "/brain")
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        threading.Thread(target=lambda: send(CHAT_ID, _safe_text(echo_brain.handle, cmd, lambda m: send(CHAT_ID, m))),
                         daemon=True).start()
        return True
    if re.match(r"^/?done\s+#?\d{1,2}\b", lower) or lower.startswith("/plan") or re.search(
            r"\b(this week'?s plan|weekly plan|what'?s the plan)\b", lower):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        threading.Thread(target=lambda: send(CHAT_ID, _safe_text(echo_ceo.handle, text) or "Send /plan for this week's plan."),
                         daemon=True).start()
        return True
    if lower.startswith("/health") or re.search(r"\b(health ?check|how are you running|are you (ok|okay|working))\b", lower):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        threading.Thread(target=lambda: send(CHAT_ID, _safe_text(echo_health.report)), daemon=True).start()
        return True
    if lower.startswith("/backup") or re.search(r"\bback ?up (now|echo|everything|my stuff)\b", lower):
        def do_backup():
            try:
                send(CHAT_ID, echo_backup.backup_now()[1] + "\n(Your keys and passwords are never included.)")
            except Exception as exc:
                echo_log.error("backup", exc)
                send(CHAT_ID, "❌ Backup failed: " + str(exc)[:200])
        threading.Thread(target=do_backup, daemon=True).start()
        return True
    if lower.startswith("/errors") or re.search(r"\b(what'?s|anything|is anything) (broken|wrong)\b", lower):
        send(CHAT_ID, echo_log.summary(72) or "✅ No problems logged in the last 3 days.")
        return True
    if lower.startswith("/learned"):
        send(CHAT_ID, echo_growth.describe_learning())
        return True
    if lower.startswith("/research"):
        topic = re.sub(r"^/research\s*(add\b)?\s*", "", text, flags=re.I).strip()
        send(CHAT_ID, echo_growth.queue(topic) if topic else echo_growth.describe_research())
        return True
    m = re.match(r"^(?:can you |could you |please )?(?:research|look into|find out about)\s+(.{4,120}?)(?: for me)?[.?!]*$", lower)
    if m:
        send(CHAT_ID, echo_growth.queue(m.group(1)))
        return True
    # A correction ("that's not true") becomes a lesson. A question ("be honest, is this
    # a good idea?") isn't a correction, so it goes on to be answered normally.
    if echo_growth.is_feedback(text) and "?" not in text:
        last = next((h["content"] for h in reversed(history) if h["role"] == "assistant"), "")
        send(CHAT_ID, echo_growth.record_feedback(text, last))
        return True
    if lower.startswith("/memories"):
        send(CHAT_ID, echo_memory.describe())
        return True
    m = re.match(r"^/forget\s+#?(\d+)$", lower)
    if m:
        send(CHAT_ID, "Forgotten. 🗑️" if echo_memory.forget(int(m.group(1)))
             else "I couldn't find memory #" + m.group(1) + ". Send /memories to see the numbers.")
        return True
    reply = echo_personality.remember(text) or echo_personality.set_name(text)
    if reply:
        send(CHAT_ID, reply)
        return True
    if lower.startswith("/mood"):
        send(CHAT_ID, "I'm feeling " + echo_personality.MOODS[echo_personality.mood()] + " right now 🙂")
        return True
    if lower.startswith(("/office", "/officevideo")) or re.search(
            r"\b(photo|picture|pic|video|clip|screenshot)s? of (the |my )?(digital |echo |3d )?(office|hq|headquarters|building)\b", lower):
        kind = "video" if ("video" in lower or "clip" in lower or lower.startswith("/officevideo")) else "photo"
        dept = next((k for k in ("sales", "marketing", "content", "editing", "research", "web", "operations", "finance",
                                 "shopify", "trading", "support", "relax", "ceo") if k in lower), "")
        if dept == "web":
            dept = "webdesign"
        try:
            req = urllib.request.Request("http://127.0.0.1:5000/api/office/capture-request",
                                         data=json.dumps({"kind": kind, "dept": dept}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                info = json.load(r)
        except Exception:
            send(CHAT_ID, "Echo HQ's server isn't answering, so I can't film the office right now.")
            return True
        if not info.get("page_open"):
            import webbrowser
            webbrowser.open("http://127.0.0.1:5000/?capture=1")
        send(CHAT_ID, ("🎥 Filming the office for you… (about 15 seconds)" if kind == "video"
                       else "📸 Snapping the office for you…"))
        return True
    picture = echo_photos.picture_request(text)
    if picture:
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "upload_photo"})

        def make():
            try:
                path = echo_photos.make_picture(picture)
                send_photo(CHAT_ID, path, "Here you go: " + picture[:200])
            except Exception as exc:
                send(CHAT_ID, "I couldn't make that picture: " + str(exc)[:200])
        threading.Thread(target=make, daemon=True).start()
        return True
    if echo_photos.VIDEO_WORDS.search(text) and "clip" not in lower:
        send(CHAT_ID, "I can't make videos yet, sorry! 😅 I can make you a picture instead: "
                      "try \"send me a picture of ...\", or /screenshot to see your PC screen.")
        return True
    if lower.startswith("/getvision"):
        if echo_photos.has_vision():
            send(CHAT_ID, "I can already see photos. Send me one!")
            return True
        send(CHAT_ID, "Downloading " + echo_photos.vision_model() + " (" + echo_photos.VISION_SIZE +
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
        selling_all = (echo_trading.pending() or {}).get("side") == "sell_all"
        send(CHAT_ID, "Selling everything…" if selling_all else "Placing the trade…", NO_KEYBOARD)

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
    if lower.startswith(("/market", "/trade market")):
        send(CHAT_ID, "Checking the market…")

        def market():
            try:
                send(CHAT_ID, echo_trading.market_overview())
                rows, meta = echo_trading.candles("SPY")
                import echo_chart
                path = Path(tempfile.gettempdir()) / "echo_market.png"
                path.write_bytes(echo_chart.candle_chart(rows))
                _upload("sendPhoto", "photo", CHAT_ID, path, "image/png", "S&P 500 (SPY), last 60 days")
            except Exception as exc:
                send(CHAT_ID, "Couldn't check the market: " + str(exc)[:200])
        threading.Thread(target=market, daemon=True).start()
        return True
    if lower.startswith("/trade propose") or lower.startswith("/trade idea"):
        send(CHAT_ID, "Scanning the watchlist for the best setup…")
        threading.Thread(target=lambda: _safe(echo_trading.send_idea_to_phone), daemon=True).start()
        return True
    if echo_trading.AMOUNT_RE.search(text) or echo_trading.SELL_RE.match(text):
        telegram("sendChatAction", {"chat_id": CHAT_ID, "action": "typing"})
        reply = echo_trading.handle(text)
        if reply and not echo_trading.sent_to_phone[0]:
            send(CHAT_ID, reply, echo_trading.TRADE_KEYBOARD if echo_trading.pending() else None)
        if reply:
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
             "• send me a picture of ... - I make you an image\n"
             "• remember that ... - I'll remember it about you\n"
             "• /office - photo of the digital office · /officevideo - a video tour\n"
             "• /screenshot - photo of your PC screen\n"
             "• /photos and /photo 1 - get saved photos back\n"
             "• /roblox a snowy obby - build a Roblox map (/maps lists them)\n"
             "• /leads - today's 20 businesses (/findleads gets new ones)\n"
             "• /trade analyse BHP.AX - chart read + risk plan\n"
             "• /market - UP / DOWN / WAIT for each stock, with a chart\n"
             "• /connections - what every office is connected to, and what's missing\n"
             "• /shop, /orders, or just 'add a dog jacket to my store, $39.95, 20 in stock'\n"
             "• put $500 into NVDA - Echo buys, then sells for you at the stop or target\n"
             "• email Joe's Plumbing - Sales writes the email; you tap Yes to send\n"
             "• /trade propose - best trade idea with a chart; tap Place trade to approve\n"
             "• /ceo - today's business summary · /status - is Echo running?\n"
             "• /pipeline · pitch <business> · mark <business> won\n"
             "• /money · income 500 website for Joe · expense 30 OpusClip\n"
             "• enquiry <name>: <message> · /tickets · my goal is ...\n"
             "• /callme - I ring your phone\n"
             "• send a chart screenshot with 'what do I do?' (or the ticker) - the Trading Analyst reads it\n"
             "• stop trading - pause all trading at once · sell everything · resume trading\n"
             "• remember that ... · /memories - what I remember · /forget 12\n"
             "• /clip LINK or /clip latest - OpusClip makes short clips · /clips · /post 1 youtube instagram [at 6pm]\n"
             "• search youtube for ... · google ... · open my shopify admin · /screen - see your PC screen\n"
             "• /guide connect my shopify store - I look at your screen and tell you where to click (next / stop)\n"
             "• /plan - the CEO's plan for this week from your goals · /done 2 - tick off task 2\n"
             "• /health - full check-up · /errors - anything that went wrong · /backup - back up now\n"
             "• /brain - check the PC and get a smarter free AI brain (/brain upgrade · /brain small)\n"
             "• /research - what I'm researching · /research add TOPIC · /learned - what I've learned\n"
             "• that's not true / /feedback ... - correct me and I'll learn from it\n"
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
            echo_business.heartbeat("telegram")
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
                        needs = echo_phone.briefing()
                        send(CHAT_ID, echo_phone.call_me(
                            "Hi, it's Echo. You asked me to call. " + ("Quick update: " + "; ".join(needs[:3]) + ". "
                                                                     if needs else "") + "What's up?",
                            topic="Current needs: " + "; ".join(needs),
                            approval="trade" if any("trade idea" in n for n in needs) else None))
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
            if "timed out" not in str(exc).lower() and "10054" not in str(exc):
                print("Echo Telegram chat error:", exc, flush=True)  # brief internet drops are normal
            time.sleep(5)


if __name__ == "__main__":
    echo_log.install()
    main()
