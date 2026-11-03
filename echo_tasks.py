# ECHO AI - TASK MANAGEMENT SYSTEM

import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

# Stored next to this file so Echo works from any starting folder.
TASK_FILE = Path(__file__).with_name("echo_tasks.json")

from echo_employees import EMPLOYEES

EMPLOYEE_ROLES = {key: value["name"] for key, value in EMPLOYEES.items()}


def load_tasks():
    if not os.path.exists(TASK_FILE):
        return {}

    try:
        with open(TASK_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, ValueError):
        # Keep the damaged file for inspection and start fresh.
        damaged = TASK_FILE.with_suffix(".damaged.json")
        try:
            os.replace(TASK_FILE, damaged)
            print("echo_tasks.json was damaged; moved to", damaged.name)
        except OSError:
            pass
        return {}
    return data if isinstance(data, dict) else {}


def save_tasks(tasks):
    # Write to a temp file first so a crash cannot leave half-written tasks.
    temp = TASK_FILE.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as file:
        json.dump(tasks, file, indent=2)
    os.replace(temp, TASK_FILE)


def create_task(employee_id, description):
    if employee_id not in EMPLOYEE_ROLES:
        raise ValueError("Unknown employee")

    tasks = load_tasks()

    task_id = str(uuid.uuid4())

    tasks[task_id] = {
        "id": task_id,
        "employee_id": employee_id,
        "employee": EMPLOYEE_ROLES[employee_id],
        "description": description,
        "status": "waiting_for_approval",
        "created": datetime.now(
            timezone.utc
        ).isoformat()
    }

    save_tasks(tasks)

    return tasks[task_id]


def approve_task(task_id):
    tasks = load_tasks()

    if task_id not in tasks:
        return False

    if tasks[task_id]["status"] != "waiting_for_approval":
        return False

    tasks[task_id]["status"] = "approved"
    save_tasks(tasks)

    return True


def reject_task(task_id):
    tasks = load_tasks()

    if task_id not in tasks:
        return False

    if tasks[task_id]["status"] != "waiting_for_approval":
        return False

    tasks[task_id]["status"] = "rejected"
    save_tasks(tasks)

    return True


def get_employee_tasks(employee_id):
    tasks = load_tasks()

    return [
        task for task in tasks.values()
        if task["employee_id"] == employee_id
    ]


def get_pending_tasks():
    tasks = load_tasks()

    return [
        task for task in tasks.values()
        if task["status"] == "waiting_for_approval"
    ]


def echo_task_status():
    tasks = load_tasks()

    return {
        "total_tasks": len(tasks),
        "pending_approval": len(get_pending_tasks()),
        "approved": sum(
            task["status"] == "approved"
            for task in tasks.values()
        ),
        "employees": EMPLOYEE_ROLES
    }
