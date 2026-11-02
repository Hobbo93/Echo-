# ==========================================
# ECHO AI - DAILY SCHEDULER
# File: echo_scheduler.py
# ==========================================

import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from echo_tasks import create_task, load_tasks
from echo_telegram import send_report, send_alert

TIMEZONE = ZoneInfo("Australia/Adelaide")

# Files live next to this script so Echo works from any starting folder.
ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = ROOT / "echo_schedule.json"

# The same error is sent to Telegram at most once per hour.
ALERT_COOLDOWN_SECONDS = 3600
_last_alerts = {}

DAILY_TARGETS = {
    "businesses_to_research": 20,
    "top_leads": 5,
    "ai_generated_videos": 50,
    "edited_video_clips": 50,
    "report_times": ["06:30", "13:00", "17:30"]
}


def current_time():
    return datetime.now(TIMEZONE)


def today():
    return current_time().date().isoformat()


def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return {}

    try:
        with open(SCHEDULE_FILE, "r") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        # A damaged schedule file should not stop the scheduler.
        return {}


def save_schedule(schedule):
    temp = SCHEDULE_FILE.with_suffix(".tmp")
    with open(temp, "w") as file:
        json.dump(schedule, file, indent=4)
    os.replace(temp, SCHEDULE_FILE)


def task_exists(description):
    tasks = load_tasks()

    return any(
        task["description"] == description
        for task in tasks.values()
    )


def queue_task(employee, description):
    if task_exists(description):
        return None

    return create_task(employee, description)


# ==========================================
# EMPLOYEE 1 - CONTENT CREATOR
# ==========================================

def schedule_content():
    date = today()

    for number in range(1, 51):
        queue_task(
            "employee_1",
            f"{date}: AI video idea {number}. "
            "Prepare an original video concept. "
            "Suggest the best social media account. "
            "Wait for approval."
        )

    for number in range(1, 51):
        queue_task(
            "employee_1",
            f"{date}: Edited clip idea {number}. "
            "Identify suitable authorised footage. "
            "Prepare an editing plan. "
            "Wait for approval."
        )


# ==========================================
# EMPLOYEE 4 - BUSINESS LEADS
# ==========================================

def schedule_leads():
    date = today()

    queue_task(
        "employee_4",
        f"{date}: Research up to 20 businesses "
        "that may need websites or AI receptionists. "
        "Verify their public business information. "
        "Rank the best 5 opportunities. "
        "Do not build demos or contact businesses "
        "without approval."
    )


# ==========================================
# DAILY REPORT
# ==========================================

def generate_report(report_time=None):
    date = today()
    tasks = load_tasks()

    todays_tasks = [
        task for task in tasks.values()
        if task["description"].startswith(date)
    ]

    def count(status):
        return sum(task["status"] == status for task in todays_tasks)

    report = {
        "date": date,
        "report_time": report_time,
        "timezone": "Australia/Adelaide",
        "business_research_target": DAILY_TARGETS["businesses_to_research"],
        "top_leads_target": DAILY_TARGETS["top_leads"],
        "ai_video_target": DAILY_TARGETS["ai_generated_videos"],
        "edited_clip_target": DAILY_TARGETS["edited_video_clips"],
        "queued_tasks": len(todays_tasks),
        "pending_approval": count("waiting_for_approval"),
        "approved": count("approved"),
        "rejected": count("rejected"),
        "note": (
            "This is a scheduling report only. "
            "Research and video generation tools "
            "are not connected yet, so no work "
            "has been completed automatically."
        )
    }

    filename = ROOT / f"echo_report_{date}.json"

    with open(filename, "w") as file:
        json.dump(report, file, indent=4)

    return report


# ==========================================
# DAILY SCHEDULING
# ==========================================

def run_daily_schedule():
    schedule = load_schedule()
    date = today()

    if schedule.get("last_queued") != date:
        schedule_content()
        schedule_leads()

        schedule["last_queued"] = date
        save_schedule(schedule)

        print("Echo daily tasks queued.")

    now = current_time().strftime("%H:%M")

    due = [
        report_time for report_time in DAILY_TARGETS["report_times"]
        if now >= report_time
        and schedule.get("last_report_" + report_time) != date
    ]

    if not due:
        return

    # If Echo starts late (e.g. PC switched on at 6 PM), send only the
    # latest report instead of every missed one at once.
    for report_time in due:
        schedule["last_report_" + report_time] = date
    save_schedule(schedule)

    latest = due[-1]
    report = generate_report(latest)
    print("Echo report " + latest + ":")
    print(json.dumps(report, indent=4))
    send_report(report)


def alert_once(message):
    """Send an alert, but not the same one more than once per hour."""
    now = time.monotonic()
    last = _last_alerts.get(message)
    if last is not None and now - last < ALERT_COOLDOWN_SECONDS:
        return False
    _last_alerts[message] = now
    return send_alert(message)


# ==========================================
# START SCHEDULER
# ==========================================

if __name__ == "__main__":
    print("ECHO AI SCHEDULER STARTED")
    print("Timezone: Australia/Adelaide")
    print("Reports: 6:30 AM, 1 PM, 5:30 PM")
    print("Approval required for all actions")

    while True:
        try:
            run_daily_schedule()
        except Exception as error:
            print("Scheduler error:", error)
            alert_once("Scheduler error: " + str(error))

        time.sleep(60)
      
