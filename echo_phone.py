"""Echo phone line: Echo can ring your mobile, and you can ring Echo.

Uses Twilio for the phone number (paid, ~AU$2/month + per-minute) and a free
Cloudflare tunnel so Twilio can reach this PC. Speech is handled by Twilio;
Echo's answers come from your local Ollama. See PHONE_SETUP.md.

Run: py echo_phone.py   (start_echo.bat starts it automatically once set up)

Security:
- This is a separate small server (port 5001). Only its /phone/ routes are
  reachable through the tunnel; the rest of Echo stays private.
- Every request must carry a valid Twilio signature.
- Only calls from your own number are answered.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path
import echo_brain
import echo_log

CONFIG = Path.home() / ".echo_telegram.json"
URL_FILE = Path.home() / ".echo_phone_url"
PORT = 5001
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
VOICE = os.getenv("ECHO_PHONE_VOICE", "Polly.Olivia-Neural")  # Australian English
LANGUAGE = "en-AU"

SYSTEM_PROMPT = (
    "You are Echo, a friendly personal AI assistant, talking to your owner on a "
    "phone call. Speak like a person on the phone: one to three short, natural "
    "sentences. No lists, headings, emojis or markdown. You cannot perform "
    "external actions such as trades, purchases, posts or contacting people; "
    "never claim you did."
)

calls = {}  # CallSid -> conversation history
CALL_CONTEXT = Path.home() / ".echo_calls.json"   # why each call was made (shared between Echo's windows)
CALL_LOG = Path.home() / ".echo_call_log.json"     # when Echo last rang, to avoid pestering
QUIET_START, QUIET_END = 21, 8                      # no calls 9 PM - 8 AM unless urgent
MAX_CALLS_PER_DAY = 6


def _persona(message=""):
    try:
        import echo_personality
        return echo_personality.persona(spoken=True, message=message)
    except Exception:
        return SYSTEM_PROMPT


# ==========================================
# SETTINGS
# ==========================================

def settings():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    get = lambda key, env: (os.getenv(env, "") or str(data.get(key, ""))).strip()
    return {
        "sid": get("twilio_account_sid", "TWILIO_ACCOUNT_SID"),
        "token": get("twilio_auth_token", "TWILIO_AUTH_TOKEN"),
        "number": get("twilio_number", "TWILIO_NUMBER"),
        "my_phone": get("my_phone", "ECHO_MY_PHONE"),
    }


def is_configured():
    s = settings()
    return all(s.values())


def normalise_phone(raw):
    """Australian mobile/landline (0414 123 456, 61414..., +61 414...) -> +61414123456, or '' if it isn't one."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if digits.startswith("+"):
        num = "+" + re.sub(r"\D", "", digits)
    elif digits.startswith("61") and len(digits) == 11:
        num = "+" + digits
    elif digits.startswith("0") and len(digits) == 10:
        num = "+61" + digits[1:]
    else:
        return ""
    return num if 11 <= len(num) <= 16 else ""


def set_my_phone(raw):
    """Save the owner's number on this PC (never in the code). Returns a reply."""
    num = normalise_phone(raw)
    if not num:
        return "That doesn't look like a phone number. Send it like: my number is 0414 123 456"
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    data["my_phone"] = num
    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    shown = num[:-6] + " " + num[-6:-3] + " " + num[-3:]
    s = settings()
    if s["sid"] and s["token"] and s["number"]:
        return f"📱 Saved: Echo will ring {shown}. Send /callme to test it."
    return (f"📱 Saved your number ({shown}) on the PC. Echo can't ring it yet: phone calls need a Twilio "
            "phone number, which isn't set up (PHONE_SETUP.md). Twilio costs money (about AU$2 a month plus "
            "calls). Free instead: send Echo a voice note and it replies with a voice note.")


def public_url():
    try:
        return URL_FILE.read_text(encoding="utf-8").strip().rstrip("/")
    except OSError:
        return ""


# ==========================================
# TWILIO
# ==========================================

def twilio(method, path, params=None):
    s = settings()
    url = f"https://api.twilio.com/2010-04-01/Accounts/{s['sid']}/{path}"
    data = urllib.parse.urlencode(params or {}).encode() if method == "POST" else None
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
    auth = base64.b64encode(f"{s['sid']}:{s['token']}".encode()).decode()
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Basic " + auth})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.load(exc).get("message", "")
        except ValueError:
            detail = ""
        raise RuntimeError(f"Twilio error {exc.code}: {detail}") from None


def valid_signature(url, params, signature):
    """Check X-Twilio-Signature (HMAC-SHA1 of URL + sorted POST params)."""
    token = settings()["token"]
    payload = url + "".join(key + params[key] for key in sorted(params))
    digest = hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


def say(text):
    return f'<Say voice="{VOICE}" language="{LANGUAGE}">{escape(text)}</Say>'


def gather(prompt_text="", base=None):
    action = (base or public_url()) + "/phone/reply"
    inner = say(prompt_text) if prompt_text else ""
    return (f'<Gather input="speech" action="{escape(action)}" method="POST" '
            f'language="{LANGUAGE}" speechTimeout="auto" actionOnEmptyResult="true">'
            f"{inner}</Gather>")


def twiml(*parts):
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(parts) + "</Response>"


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _context(sid):
    return _read(CALL_CONTEXT, {}).get(sid, {})


def _save_context(sid, ctx):
    data = _read(CALL_CONTEXT, {})
    data[sid] = ctx
    data = dict(list(data.items())[-30:])
    CALL_CONTEXT.write_text(json.dumps(data), encoding="utf-8")


def call_me(message="Hi, it's Echo. What can I do for you?", topic="", approval=None):
    """Ring your phone and start a conversation. Returns a status message.

    topic: background the AI should know during the call.
    approval: "trade" or "update" - saying yes on the call approves it.
    """
    if not is_configured():
        return "Echo's phone line isn't set up yet. See PHONE_SETUP.md."
    base = public_url()
    if not base:
        return "Echo's phone line isn't running. Start Echo with start_echo.bat."
    s = settings()
    try:
        call = twilio("POST", "Calls.json", {
            "To": s["my_phone"], "From": s["number"],
            "Twiml": twiml(gather(message, base), say("Okay, talk soon."), "<Hangup/>"),
        })
    except Exception as exc:
        return "Echo couldn't ring you: " + str(exc)
    _save_context(call.get("sid", ""), {"topic": topic or message, "opening": message, "approval": approval})
    log = _read(CALL_LOG, [])
    log.append(time.time())
    CALL_LOG.write_text(json.dumps(log[-50:]), encoding="utf-8")
    return "Calling you now 📞"


def may_call(urgent=False):
    """Respect quiet hours and a daily limit so Echo doesn't pester you."""
    if not is_configured() or not public_url():
        return False
    hour = time.localtime().tm_hour
    if not urgent and (hour >= QUIET_START or hour < QUIET_END):
        return False
    today = [t for t in _read(CALL_LOG, []) if t > time.time() - 86400]
    return len(today) < MAX_CALLS_PER_DAY


def briefing():
    """What the AI employees need from you right now, said like a person on the phone."""
    needs = []
    try:
        import echo_trading
        p = echo_trading.pending()
        if p:
            needs.append(f"the Day Trading Desk has a trade idea: {p['symbol']} "
                         f"{'up' if p.get('direction', 'UP') == 'UP' else 'down'}, stop {p['stop']:.2f}, "
                         f"target {p['target']:.2f}")
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)
    try:
        from echo_telegram import PENDING_FILE
        if PENDING_FILE.exists():
            needs.append("there's an Echo update waiting for your yes or no")
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)
    try:
        import echo_business
        urgent = [t for t in echo_business._tickets() if t["status"] == "open" and t["urgent"]]
        if urgent:
            needs.append(f"Customer Support has {len(urgent)} urgent enquiry, from {urgent[0]['customer']}")
        fu = echo_business.follow_ups()
        if fu.startswith("Follow-ups due"):
            needs.append(f"the Sales Agent has {len(fu.splitlines()) - 1} follow-ups due")
        bad = [l[2:] for l in echo_business.status_text().splitlines() if l.startswith("🔴")]
        if bad:
            needs.append("Operations says " + bad[0])
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)
    try:
        from echo_tasks import load_tasks
        waiting = sum(t["status"] == "waiting_for_approval" for t in load_tasks().values())
        if waiting:
            needs.append(f"{waiting} tasks are waiting for approval")
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)
    return needs


# ==========================================
# AI
# ==========================================

def ask_echo(history, message):
    messages = [{"role": "system", "content": _persona(message)}, *history,
                {"role": "user", "content": message}]
    echo_brain.mark_active()
    payload = {"model": echo_brain.fast_model(), "messages": messages, "stream": False,
               "keep_alive": echo_brain.KEEP_ALIVE,
               "options": {"num_predict": 120}}  # short answers keep calls snappy
    req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:  # Twilio waits 15s at most
        reply = json.load(r).get("message", {}).get("content", "").strip()
    try:
        import echo_growth
        if echo_growth.check_reply(reply) != reply:  # it claimed something that didn't happen
            reply += " Actually, to be honest, I can't really do that from a call, so it hasn't happened."
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)
    _log("phone", message, reply)
    return reply


def _log(channel, message, reply):
    try:
        import echo_memory
        # No summary during a call (it would slow replies); the scheduler does it afterwards.
        echo_memory.log_turn(channel, message, reply, summarise=False)
    except Exception as _exc:
        echo_log.error("echo_phone", _exc)


# ==========================================
# PHONE SERVER (the only part reachable from the internet)
# ==========================================

def _do_approval(kind, choice):
    """Carry out a yes/no given on the phone; also tells you on Telegram."""
    try:
        if kind == "update":
            from echo_telegram import DECISION_FILE, PENDING_FILE
            if not PENDING_FILE.exists():
                return "That update was already handled."
            DECISION_FILE.write_text(choice, encoding="utf-8")
            return "Done, installing the update." if choice == "yes" else "Okay, I'll skip that update."
        if kind == "shopify":
            import echo_shopify
            if choice == "no":
                return echo_shopify.skip()
            result = echo_shopify.approve()
            try:
                import echo_trading
                echo_trading._telegram_text("Approved on the phone:\n" + result)
            except Exception as _exc:
                echo_log.error("echo_phone", _exc)
            return result.splitlines()[0].replace("✅ ", "Done. ")
        if kind == "trade":
            import echo_trading
            if choice == "no":
                echo_trading.skip()
                return "Okay, skipped. No trade."
            msg, png = echo_trading.approve()
            try:
                echo_trading._telegram_text("Approved on the phone:\n" + msg)
                if png:
                    echo_trading._telegram_photo(png, "Your trade: blue entry, red stop, green target")
            except Exception as _exc:
                echo_log.error("echo_phone", _exc)
            return "Done. I've sent the details and a chart to your Telegram."
    except Exception as exc:
        return "Sorry, that didn't work: " + str(exc)[:120]
    return "Okay."


def create_app():
    from flask import Flask, request, Response, abort

    app = Flask("echo_phone")

    def checked():
        base = public_url()
        params = request.form.to_dict()
        url = base + request.full_path.rstrip("?")
        if not base or not valid_signature(url, params, request.headers.get("X-Twilio-Signature")):
            abort(403)
        return params

    def xml(body):
        return Response(body, mimetype="text/xml")

    @app.post("/phone/incoming")
    def incoming():
        params = checked()
        if params.get("From") != settings()["my_phone"]:
            return xml(twiml(say("Sorry, this line is private."), "<Hangup/>"))
        needs = briefing()
        hello = ("Hi, it's Echo. " + ("Quick update: " + "; ".join(needs[:3]) + ". What would you like to do?"
                                      if needs else "Everything's running smoothly. What can I do for you?"))
        _save_context(params.get("CallSid", ""), {"topic": "You called Echo. Current needs: " + "; ".join(needs),
                                                  "opening": hello,
                                                  "approval": "trade" if any("trade idea" in n for n in needs) else None})
        return xml(twiml(gather(hello), say("Okay, talk soon."), "<Hangup/>"))

    @app.post("/phone/reply")
    def reply():
        params = checked()
        mine = settings()["my_phone"]
        if mine not in (params.get("From"), params.get("To")):
            return xml(twiml("<Hangup/>"))
        sid = params.get("CallSid", "")
        heard = params.get("SpeechResult", "").strip()
        if not heard:
            return xml(twiml(gather("Sorry, I didn't catch that."), say("Talk soon."), "<Hangup/>"))
        if re.match(r"^(bye|goodbye|that's all|hang up)\b", heard, re.I):
            calls.pop(sid, None)
            return xml(twiml(say("No worries. Talk soon!"), "<Hangup/>"))
        ctx = _context(sid)
        if sid not in calls and ctx:
            calls[sid] = [{"role": "assistant", "content": ctx.get("opening", "")},
                          {"role": "user", "content": "(Background for you, Echo: " + ctx.get("topic", "") + ")"},
                          {"role": "assistant", "content": "Got it."}]
        history = calls.setdefault(sid, [])
        approval = ctx.get("approval")
        if approval:
            from echo_telegram import yes_no
            choice = yes_no(heard)
            if choice:
                ctx["approval"] = None
                _save_context(sid, ctx)
                spoken = _do_approval(approval, choice)
                return xml(twiml(gather(spoken + " Anything else?"), say("Talk soon."), "<Hangup/>"))
        try:
            answer = ask_echo(history[-12:], heard) or "Sorry, I'm not sure."
        except Exception:
            answer = "Sorry, my brain isn't responding. Check that Ollama is running on the PC."
        history += [{"role": "user", "content": heard}, {"role": "assistant", "content": answer}]
        return xml(twiml(gather(answer), say("Are you still there? Talk soon."), "<Hangup/>"))

    @app.post("/phone/status")
    def status():
        checked()
        calls.pop(request.form.get("CallSid", ""), None)
        return ("", 204)

    return app


# ==========================================
# TUNNEL + START
# ==========================================

def start_tunnel():
    """Start a free Cloudflare quick tunnel and return its public https URL."""
    exe = shutil.which("cloudflared")
    if not exe:
        raise SystemExit("cloudflared is not installed. Run setup_echo.bat and choose Y for phone calls.")
    process = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{PORT}"],
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    found = {}

    def watch():
        for line in process.stdout:
            match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
            if match and "url" not in found:
                found["url"] = match.group(0)

    threading.Thread(target=watch, daemon=True).start()
    for _ in range(60):
        if "url" in found:
            return found["url"]
        time.sleep(1)
    process.kill()
    raise SystemExit("Could not start the Cloudflare tunnel. Check the internet connection.")


def point_number_at(base):
    """Tell Twilio to send calls to this PC's current tunnel address."""
    s = settings()
    numbers = twilio("GET", "IncomingPhoneNumbers.json", {"PhoneNumber": s["number"]})
    items = numbers.get("incoming_phone_numbers", [])
    if not items:
        raise SystemExit(f"Twilio number {s['number']} not found in your Twilio account.")
    twilio("POST", f"IncomingPhoneNumbers/{items[0]['sid']}.json", {
        "VoiceUrl": base + "/phone/incoming", "VoiceMethod": "POST",
        "StatusCallback": base + "/phone/status", "StatusCallbackMethod": "POST",
    })


def main():
    if not is_configured():
        raise SystemExit("Phone calls aren't set up. See PHONE_SETUP.md, then run setup_echo.bat.")
    print("Starting Echo's phone line...", flush=True)
    base = start_tunnel()
    URL_FILE.write_text(base, encoding="utf-8")
    point_number_at(base)
    print("Echo phone line ready. Ring", settings()["number"], "to talk to Echo.", flush=True)
    print("Keep this window open while you want calls to work.", flush=True)
    try:
        create_app().run(host="127.0.0.1", port=PORT, debug=False)
    finally:
        URL_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    echo_log.install()
    main()
