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

CONFIG = Path.home() / ".echo_telegram.json"
URL_FILE = Path.home() / ".echo_phone_url"
PORT = 5001
OLLAMA = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MODEL = os.getenv("ECHO_MODEL", "llama3.2")
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


def call_me(message="Hi, it's Echo. What can I do for you?"):
    """Ring your phone and start a conversation. Returns a status message."""
    if not is_configured():
        return "Echo's phone line isn't set up yet. See PHONE_SETUP.md."
    base = public_url()
    if not base:
        return "Echo's phone line isn't running. Start Echo with start_echo.bat."
    s = settings()
    try:
        twilio("POST", "Calls.json", {
            "To": s["my_phone"], "From": s["number"],
            "Twiml": twiml(gather(message, base), say("Okay, talk soon."), "<Hangup/>"),
        })
    except Exception as exc:
        return "Echo couldn't ring you: " + str(exc)
    return "Calling you now 📞"


# ==========================================
# AI
# ==========================================

def ask_echo(history, message):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history,
                {"role": "user", "content": message}]
    payload = {"model": MODEL, "messages": messages, "stream": False,
               "options": {"num_predict": 120}}  # short answers keep calls snappy
    req = urllib.request.Request(OLLAMA, json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:  # Twilio waits 15s at most
        return json.load(r).get("message", {}).get("content", "").strip()


# ==========================================
# PHONE SERVER (the only part reachable from the internet)
# ==========================================

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
        return xml(twiml(gather("Hi, it's Echo. What can I do for you?"),
                         say("Okay, talk soon."), "<Hangup/>"))

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
        history = calls.setdefault(sid, [])
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
    main()
