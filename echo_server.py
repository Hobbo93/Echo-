# ==========================================
# ECHO AI - MAIN EMPLOYEE SERVER
# File: echo_server.py
# ==========================================

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
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
BROWSER_PATHS = {"/health", "/api/chat", "/api/employees"}


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
DEFAULT_MODEL = os.getenv("ECHO_MODEL", "llama3.2")
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
        "or contact businesses."
    )

    payload = {
        "model": employee.get(
            "model", DEFAULT_MODEL
        ),
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
        "stream": False
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

    if not message:
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

    try:

        reply = ask_ollama(
            message,
            employee,
            history
        )

        return jsonify({
            "reply": reply,
            "employee_id": employee_id,
            "employee": employee["name"]
        })

    except urllib.error.HTTPError as error:

        detail = error.read().decode("utf-8", "replace")[:300]
        if error.code == 404:
            detail = (
                f"Model '{employee.get('model', DEFAULT_MODEL)}' is not "
                f"installed. Run: ollama pull {employee.get('model', DEFAULT_MODEL)}"
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
