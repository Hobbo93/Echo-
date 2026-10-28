# ==========================================
# ECHO AI - AUTOMATION CONTROLLER
# File: echo_automation.py
# ==========================================

from datetime import datetime, timezone

from echo_tasks import (
    create_task,
    load_tasks,
    approve_task,
    reject_task,
    get_pending_tasks
)

EMPLOYEES = {
    "employee_1": "Content Creator",
    "employee_2": "Trading Analyst",
    "employee_3": "Shopify Manager",
    "employee_4": "Website & Leads Manager"
}

# Actions requiring explicit approval
PROTECTED_ACTIONS = {
    "publish_video",
    "schedule_post",
    "contact_business",
    "send_email",
    "make_call",
    "build_demo",
    "publish_website",
    "execute_trade",
    "spend_money",
    "change_store"
}

# Future integrations
INTEGRATIONS = {
    "video_generator": False,
    "video_editor": False,
    "metricool": False,
    "market_data": False,
    "trading_platform": False,
    "shopify": False,
    "business_search": False,
    "website_builder": False,
    "notifications": False
}


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def create_employee_job(
    employee_id,
    description,
    action="research"
):
    if employee_id not in EMPLOYEES:
        raise ValueError("Unknown employee")

    task = create_task(
        employee_id,
        f"[{action}] {description}"
    )

    return {
        "success": True,
        "task": task,
        "requires_approval": True
    }


def approve_employee_job(task_id):
    return approve_task(task_id)


def reject_employee_job(task_id):
    return reject_task(task_id)


def pending_approvals():
    return get_pending_tasks()


def get_job_status(task_id):
    tasks = load_tasks()

    if task_id not in tasks:
        return {
            "error": "Task not found"
        }

    return tasks[task_id]


def can_execute(task_id, action):
    tasks = load_tasks()

    task = tasks.get(task_id)

    if not task:
        return False

    if action in PROTECTED_ACTIONS:
        return task["status"] == "approved"

    return True


def execute_job(task_id, action):
    tasks = load_tasks()

    task = tasks.get(task_id)

    if not task:
        return {
            "success": False,
            "error": "Task not found"
        }

    if not can_execute(task_id, action):
        return {
            "success": False,
            "status": "waiting_for_approval"
        }

    return {
        "success": False,
        "status": "integration_required",
        "message": (
            "Task is authorised for preparation, "
            "but no external execution tool "
            "is connected yet."
        )
    }


def automation_status():
    tasks = load_tasks()

    return {
        "system": "Echo AI",
        "time": timestamp(),
        "employees": EMPLOYEES,
        "integrations": INTEGRATIONS,
        "total_tasks": len(tasks),
        "pending_approvals": len(
            get_pending_tasks()
        ),
        "automation_enabled": False
    }


if __name__ == "__main__":
    print("ECHO AUTOMATION CONTROLLER")

    status = automation_status()

    print("Employees:", len(EMPLOYEES))
    print("Tasks:", status["total_tasks"])
    print(
        "Pending approvals:",
        status["pending_approvals"]
    )

    print("External integrations pending.")
