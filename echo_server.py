# ==========================================
# ECHO AI - MAIN EMPLOYEE SERVER
# File: echo_server.py
# ==========================================

import json
import os
import urllib.request
import base64
import re
import binascii
import urllib.error
from pathlib import Path
import echo_photos
import echo_roblox
import echo_leads
import echo_shopify
import echo_email
import echo_connections
import echo_trading
import echo_business
import echo_memory
import echo_growth
import echo_router
import echo_tradeshot
import echo_brain
import time as _time
import threading
from flask import Flask, request, jsonify, send_file

from echo_employees import (
    EMPLOYEES,
    list_employees,
    echo_status,
    request_approval,
    approve_task,
    reject_task,
    load_approvals
)

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent

# Office.html is opened straight from disk (origin "null") or from localhost.
# Only these origins may call the server, and only health + chat;
# approvals stay off-limits to the browser page.
ALLOWED_ORIGINS = {
    "null",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
}
BROWSER_PATHS = {"/health", "/api/chat", "/api/employees", "/api/call-me"}


@app.after_request
def allow_office_page(response):
    origin = request.headers.get("Origin", "")
    if request.path in BROWSER_PATHS and (
        origin in ALLOWED_ORIGINS
        or origin.startswith(("http://127.0.0.1:", "http://localhost:"))
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response

OLLAMA_URL = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
MAX_HISTORY = 16  # earlier messages sent back to the model for context

# ==========================================
# OLLAMA AI CONNECTION
# ==========================================

def ask_ollama(message, employee, history=()):

    system_prompt = (
        f"You are {employee['name']}.\n"
        f"Your role is: {employee['role']}.\n\n"
        f"{employee['instructions']}\n\n"
        "You are part of Echo, a personal AI "
        "assistant with specialised employees. "
        "Be helpful and practical. "
        "Never claim an external action was "
        "completed unless a connected tool "
        "actually completed it. "
        "You cannot independently execute "
        "trades, publish posts, spend money "
        "or contact businesses. "
        + echo_business.OFFICE_RULES
    )
    echo_brain.mark_active()
    try:  # honesty rules, real connections and lessons learned from the owner
        system_prompt += "\n\n" + echo_growth.prompt_block()
    except Exception:
        pass
    try:  # memories that match this message, shared by every employee
        memories = echo_memory.context_for(message, limit=5, always_limit=5)
    except Exception:
        memories = ""
    if memories:
        system_prompt += "\n\n" + memories

    payload = {
        "model": echo_brain.resolve(employee.get("model")),
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            *history,
            {
                "role": "user",
                "content": message
            }
        ],
        "stream": False,
        "keep_alive": echo_brain.KEEP_ALIVE
    }

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(
        req, timeout=120
    ) as response:

        result = json.loads(
            response.read().decode("utf-8")
        )

    return result.get(
        "message", {}
    ).get(
        "content",
        "No response received."
    )


# ==========================================
# 3D OFFICE PAGE
# ==========================================

@app.route("/", methods=["GET"])
def office():

    return send_file(ROOT / "Office.html")


# ==========================================
# SERVER HEALTH
# ==========================================

_last_beat = [0.0]


@app.before_request
def _beat():
    if _time.time() - _last_beat[0] > 60:
        _last_beat[0] = _time.time()
        try:
            echo_business.heartbeat("server")
        except OSError:
            pass


@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "online",
        "system": "Echo AI"
    })


# ==========================================
# EMPLOYEE LIST
# ==========================================

@app.route("/api/employees", methods=["GET"])
def employees():

    return jsonify({
        "employees": list_employees()
    })


# ==========================================
# EMPLOYEE DETAILS
# ==========================================

@app.route(
    "/api/employees/<employee_id>",
    methods=["GET"]
)
def employee_details(employee_id):

    employee = EMPLOYEES.get(employee_id)

    if not employee:
        return jsonify({
            "error": "Employee not found"
        }), 404

    return jsonify({
        "id": employee_id,
        "employee": employee
    })


# ==========================================
# AI CHAT
# ==========================================

@app.route("/api/connections")
def connections():
    return jsonify(echo_connections.check_all())


@app.route("/api/chat", methods=["POST", "OPTIONS"])
def chat():

    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}

    message = data.get("message", "")

    if not isinstance(message, str):
        return jsonify({
            "error": "Message must be text"
        }), 400

    message = message.strip()

    # Photos attached in Echo HQ arrive as base64 (optionally data: URLs).
    images = []
    raw_images = data.get("images", [])
    if isinstance(raw_images, list):
        for item in raw_images[:3]:
            if not isinstance(item, str):
                continue
            try:
                blob = base64.b64decode(item.split(",", 1)[-1], validate=False)
            except (ValueError, binascii.Error):
                continue
            if echo_photos.image_type(blob) and len(blob) <= echo_photos.MAX_IMAGE_BYTES:
                images.append(blob)

    if not message and not images:
        return jsonify({
            "error": "Message cannot be empty"
        }), 400

    employee_data = data.get("employee", {})
    if not isinstance(employee_data, dict):
        employee_data = {}

    employee_id = data.get("employee_id")

    history = []
    raw_history = data.get("history", [])
    if isinstance(raw_history, list):
        for item in raw_history[-MAX_HISTORY:]:
            if (isinstance(item, dict)
                    and item.get("role") in ("user", "assistant")
                    and isinstance(item.get("content"), str)):
                history.append({"role": item["role"],
                                "content": item["content"][:4000]})

    # Support the existing 3D office interface,
    # which sends an employee name and role.

    # Match by name first: office numbers can differ from Echo's employee numbers.
    if isinstance(employee_data, dict) and employee_data.get("name"):
        wanted = str(employee_data.get("name", "")).strip().lower()
        for key, employee in EMPLOYEES.items():
            if employee["name"].lower() == wanted:
                employee_id = key
                break

    if employee_id not in EMPLOYEES and isinstance(
        employee_data, dict
    ):
        selected_name = employee_data.get(
            "name", ""
        ).strip().lower()

        for key, employee in EMPLOYEES.items():

            if employee["name"].lower() == selected_name:
                employee_id = key
                break

    if employee_id not in EMPLOYEES:
        # Extra rooms added in the office start from the general assistant.
        employee_id = "employee_5"

    employee = dict(EMPLOYEES.get(employee_id))

    # Edits made in the 3D office (name, role, model, instructions)
    # override the built-in profile. Safety rules are always added
    # by ask_ollama regardless.
    for field in ("name", "role", "model", "instructions"):
        value = employee_data.get(field)
        if isinstance(value, str) and value.strip() and value.strip() != "Unassigned":
            employee[field] = value.strip()[:2000]

    if not employee:
        return jsonify({
            "error": "Unknown employee"
        }), 404

    if not employee.get("active", False):
        return jsonify({
            "error": "Employee is inactive"
        }), 403

    if data.get("voice") is True:
        employee["instructions"] = employee.get("instructions", "") + (
            "\n\nYou are talking out loud on a voice call. Reply like a "
            "person on the phone: one to three short, natural sentences. "
            "No lists, headings, emojis or markdown."
        )

    try:

        picture = None if images else echo_photos.picture_request(message)
        if picture:
            path = echo_photos.make_picture(picture)
            return jsonify({
                "reply": "Here you go: " + picture,
                "image": "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode(),
                "employee_id": employee_id, "employee": employee["name"]})

        if not images and echo_email.EMAIL_RE.match(message):
            reply = echo_email.handle(message)
            if reply:
                return jsonify({"reply": reply, "employee_id": employee_id, "employee": employee["name"]})

        if not images:
            office_reply = echo_business.handle(EMPLOYEES[employee_id]["name"], message)
            if office_reply:
                return jsonify({"reply": office_reply, "employee_id": employee_id,
                                "employee": employee["name"]})

        if employee_id == "employee_3" or (not images and echo_shopify.STORE_WORDS.search(message)
                                            and re.search(r"\b(shopify|store|furventure)\b", message, re.I)):
            saved = [echo_photos.save_photo(b, "product") for b in images]
            reply = echo_shopify.handle(message, images=saved, force=employee_id == "employee_3")
            if reply:
                return jsonify({"reply": reply, "employee_id": employee_id, "employee": employee["name"]})

        if not images and employee_id == "employee_10":
            reply = echo_trading.handle(message)
            if reply and echo_trading.sent_to_phone[0]:
                reply += "\n\n📱 Sent to your phone: tap ✅ Place trade on Telegram to approve it."
            if reply:
                return jsonify({"reply": reply, "employee_id": employee_id,
                                "employee": employee["name"]})

        if (not images and employee_id == "employee_4"
                and echo_leads.looks_like_leads_request(message)):
            fresh = any(w in message.lower() for w in ("new", "find", "more", "today"))
            result = None if fresh else echo_leads.latest()
            if result:
                reply = echo_leads.summary(result)
            elif not echo_leads.API_KEY:
                reply = ("I need a Google Places API key to find businesses. Run setup_echo.bat "
                         "and paste it in (LEADS_SETUP.md shows how to get one).")
            else:
                threading.Thread(target=lambda: echo_leads.research_leads(), daemon=True).start()
                reply = ("Finding 20 new local businesses with phones, emails and photos. It takes a "
                         "few minutes; ask me for 'my leads' shortly, or check Echo_leads in your user folder.")
            return jsonify({"reply": reply, "employee_id": employee_id, "employee": employee["name"]})

        if not images and echo_router.is_connection_question(message):
            return jsonify({"reply": echo_router.answer_connections(message),
                            "employee_id": employee_id, "employee": employee["name"]})

        if (not images and employee_id == "employee_9"
                and echo_roblox.looks_like_build_request(message)):
            result = echo_roblox.build(message)
            return jsonify({
                "reply": echo_roblox.describe(result),
                "employee_id": employee_id,
                "employee": employee["name"],
                "roblox": result
            })

        if images:
            if not echo_photos.has_vision():
                return jsonify({
                    "error": echo_photos.need_vision_message("Click \"Download photo brain\""),
                    "need_vision": True
                }), 409
            for blob in images:
                echo_photos.save_photo(blob, "from_you")
            if echo_tradeshot.wants_trade_read(message, employee["name"]):
                reply, _png = echo_tradeshot.analyse_screenshot(images[0], message)
            else:
                reply = echo_photos.look(images, message, history)
        else:
            reply = ask_ollama(
                message,
                employee,
                history
            )
            reply = echo_growth.check_reply(reply)
            echo_growth.after_reply(message, reply)
            try:
                echo_memory.log_turn("office:" + employee["name"], message, reply)
            except Exception:
                pass  # memory problems must never stop a reply

        return jsonify({
            "reply": reply,
            "employee_id": employee_id,
            "employee": employee["name"]
        })

    except urllib.error.HTTPError as error:

        detail = error.read().decode("utf-8", "replace")[:300]
        if error.code == 404:
            detail = (
                f"Model '{echo_brain.resolve(employee.get('model'))}' is not "
                f"installed. Run: ollama pull {echo_brain.resolve(employee.get('model'))}"
            )
        return jsonify({
            "error": f"Ollama error {error.code}: {detail}"
        }), 502

    except urllib.error.URLError:

        return jsonify({
            "error": (
                "Cannot connect to Ollama. "
                "Check that Ollama is running."
            )
        }), 503

    except Exception as error:

        return jsonify({
            "error": str(error)
        }), 500


# ==========================================
# PHOTO VISION MODEL (downloaded only when you click)
# ==========================================

@app.route("/api/vision", methods=["GET"])
def vision_status():
    return jsonify({
        "installed": echo_photos.has_vision(),
        "model": echo_photos.vision_model(),
        "size": echo_photos.VISION_SIZE,
        **echo_photos.pull_state
    })


@app.route("/api/vision/install", methods=["POST"])
def vision_install():
    started = echo_photos.pull_vision_in_background()
    return jsonify({"started": started, **echo_photos.pull_state})


@app.route("/api/office", methods=["GET"])
def office_feed():
    return jsonify(echo_business.office_feed())


@app.route("/api/office/rundown", methods=["GET"])
def office_rundown():
    return jsonify({"text": echo_business.rundown()})


# ---- office photos / videos for your phone ----
CAPTURE_REQ = Path.home() / ".echo_office_capture.json"
_capture_seen = [0.0]


@app.route("/api/office/capture-request", methods=["POST"])
def office_capture_request():
    """Telegram asks for a photo/video of the office; the open Echo HQ page makes it."""
    data = request.get_json(silent=True) or {}
    job = {"id": str(int(_time.time() * 1000)), "kind": "video" if data.get("kind") == "video" else "photo",
           "dept": str(data.get("dept") or ""), "time": _time.time()}
    CAPTURE_REQ.write_text(json.dumps(job), encoding="utf-8")
    page_open = _time.time() - _capture_seen[0] < 15
    return jsonify({"queued": True, "page_open": page_open})


@app.route("/api/office/capture-job", methods=["GET"])
def office_capture_job():
    _capture_seen[0] = _time.time()
    try:
        job = json.loads(CAPTURE_REQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ("", 204)
    if _time.time() - job.get("time", 0) > 300:
        CAPTURE_REQ.unlink(missing_ok=True)
        return ("", 204)
    CAPTURE_REQ.unlink(missing_ok=True)
    return jsonify(job)


@app.route("/api/office/capture", methods=["POST"])
def office_capture():
    """The page sends the finished photo/video; Echo saves it and sends it to your phone."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "photo")
    try:
        blob = base64.b64decode(str(data.get("data", "")).split(",", 1)[-1])
    except (ValueError, binascii.Error):
        return jsonify({"error": "bad data"}), 400
    if len(blob) > 45 * 1024 * 1024:
        return jsonify({"error": "too large"}), 413
    folder = Path.home() / "Echo_photos"
    folder.mkdir(exist_ok=True)
    stamp = _time.strftime("%Y%m%d-%H%M%S")
    caption = str(data.get("caption") or "Echo HQ right now")[:200]
    if kind == "video":
        path = folder / f"office_{stamp}.webm"
        path.write_bytes(blob)
        mp4 = folder / f"office_{stamp}.mp4"
        sent_path, method, field, mime = path, "sendDocument", "document", "video/webm"
        try:  # Telegram plays MP4 inline; convert with PyAV if it's installed
            import av
            with av.open(str(path)) as src, av.open(str(mp4), "w") as dst:
                vin = src.streams.video[0]
                out = dst.add_stream("libx264", rate=30)
                out.width, out.height, out.pix_fmt = vin.codec_context.width // 2 * 2, vin.codec_context.height // 2 * 2, "yuv420p"
                for frame in src.decode(vin):
                    for pkt in out.encode(frame.reformat(width=out.width, height=out.height, format="yuv420p")):
                        dst.mux(pkt)
                for pkt in out.encode(None):
                    dst.mux(pkt)
            sent_path, method, field, mime = mp4, "sendVideo", "video", "video/mp4"
        except Exception:
            pass
    else:
        sent_path = folder / f"office_{stamp}.png"
        sent_path.write_bytes(blob)
        method, field, mime = "sendPhoto", "photo", "image/png"
    ok = False
    try:
        import echo_telegram_chat as tg
        ok = tg._upload(method, field, tg.CHAT_ID, sent_path, mime, caption)
    except Exception as exc:
        print("Couldn't send office capture:", exc, flush=True)
    return jsonify({"saved": str(sent_path), "sent": bool(ok)})


@app.route("/api/leads", methods=["GET"])
def leads_latest():
    return jsonify(echo_leads.latest() or {})


# ==========================================
# ROBLOX MAP BUILDER (Studio plugin polls /api/roblox/next)
# ==========================================

@app.route("/api/roblox/next", methods=["GET"])
def roblox_next():
    job = echo_roblox.next_job()
    if not job:
        return ("", 204)
    return jsonify(job)


@app.route("/api/roblox/build", methods=["POST"])
def roblox_build():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt", "")).strip()[:500]
    if not prompt:
        return jsonify({"error": "Describe the map you want"}), 400
    result = echo_roblox.build(prompt)
    return jsonify({**result, "reply": echo_roblox.describe(result)})


@app.route("/api/roblox/install-plugin", methods=["POST"])
def roblox_install_plugin():
    try:
        path = echo_roblox.install_plugin()
    except OSError as error:
        return jsonify({"error": str(error)}), 500
    return jsonify({"installed": str(path)})


# ==========================================
# RING MY PHONE (Echo phone line, see PHONE_SETUP.md)
# ==========================================

@app.route("/api/call-me", methods=["POST", "OPTIONS"])
def call_me():

    if request.method == "OPTIONS":
        return ("", 204)

    # JSON only: browsers can't send this cross-site without CORS approval.
    if not request.is_json:
        return jsonify({"error": "JSON required"}), 415

    import echo_phone
    return jsonify({"message": echo_phone.call_me()})


# ==========================================
# APPROVAL REQUESTS
# ==========================================

@app.route(
    "/api/approvals",
    methods=["GET"]
)
def approvals():

    return jsonify({
        "approvals": load_approvals()
    })


@app.route(
    "/api/approvals/request",
    methods=["POST"]
)
def create_approval():

    data = request.get_json(silent=True) or {}

    task_id = data.get("task_id")
    employee_id = data.get("employee_id")
    description = data.get("description")

    if not all([
        task_id,
        employee_id,
        description
    ]):
        return jsonify({
            "error": "Missing required fields"
        }), 400

    if employee_id not in EMPLOYEES:
        return jsonify({
            "error": "Unknown employee"
        }), 404

    if task_id in load_approvals():
        return jsonify({
            "error": "Task ID already exists"
        }), 409

    result = request_approval(
        task_id,
        employee_id,
        description
    )

    return jsonify(result), 201


@app.route(
    "/api/approvals/<task_id>/approve",
    methods=["POST"]
)
def approve(task_id):

    success = approve_task(task_id)

    return jsonify({
        "success": success,
        "task_id": task_id
    })


@app.route(
    "/api/approvals/<task_id>/reject",
    methods=["POST"]
)
def reject(task_id):

    success = reject_task(task_id)

    return jsonify({
        "success": success,
        "task_id": task_id
    })


# ==========================================
# ECHO SYSTEM STATUS
# ==========================================

@app.route("/api/status", methods=["GET"])
def status():

    return jsonify(echo_status())


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    print("=" * 40)
    print("ECHO AI EMPLOYEE SERVER")
    print("=" * 40)

    for employee in list_employees():
        print(
            employee["id"],
            "-",
            employee["name"]
        )

    print("=" * 40)
    print("Open Echo HQ: http://127.0.0.1:5000")
    print("=" * 40)

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )
