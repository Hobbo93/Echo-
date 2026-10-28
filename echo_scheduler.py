# ==========================================
# ECHO AI - DAILY SCHEDULER
# File: echo_scheduler.py
# ==========================================

import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from echo_tasks import create_task, load_tasks

TIMEZONE = ZoneInfo("Australia/Adelaide")

SCHEDULE_FILE = "echo_schedule.json"

DAILY_TARGETS = {
    "businesses_to_research": 100,
    "top_leads": 10,
    "ai_generated_videos": 50,
    "edited_video_clips": 50,
    "report_time": "19:00"
}


def current_time():
    return datetime.now(TIMEZONE)


def today():
    return current_time().date().isoformat()


def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return {}

    with open(SCHEDULE_FILE, "r") as file:
        return json.load(file)


def save_schedule(schedule):
    with open(SCHEDULE_FILE, "w") as file:
        json.dump(schedule, file, indent=4)


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
        f"{date}: Research up to 100 businesses "
        "that may need websites or AI receptionists. "
        "Verify their public business information. "
        "Rank the best 10 opportunities. "
        "Do not build demos or contact businesses "
        "without approval."
    )


# ==========================================
# DAILY REPORT
# ==========================================

def generate_report():
    date = today()
    tasks = load_tasks()

    todays_tasks = [
        task for task in tasks.values()
        if task["description"].startswith(date)
    ]

    report = {
        "date": date,
        "timezone": "Australia/Adelaide",
        "business_research_target": 100,
        "top_leads_target": 10,
        "ai_video_target": 50,
        "edited_clip_target": 50,
        "queued_tasks": len(todays_tasks),
        "completed_research": 0,
        "completed_videos": 0,
        "note": (
            "This is a scheduling report only. "
            "Research and video generation tools "
            "are not connected yet."
        )
    }

    filename = f"echo_report_{date}.json"

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

    now = current_time()

    if (
        now.hour >= 19
        and schedule.get("last_report") != date
    ):
        report = generate_report()

        schedule["last_report"] = date
        save_schedule(schedule)

        print("Echo 7 PM report:")
        print(json.dumps(report, indent=4))


# ==========================================
# START SCHEDULER
# ==========================================

if __name__ == "__main__":
    print("ECHO AI SCHEDULER STARTED")
    print("Timezone: Australia/Adelaide")
    print("Daily report: 7 PM")
    print("Approval required for all actions")

    while True:
        try:
            run_daily_schedule()
        except Exception as error:
            print("Scheduler error:", error)

        time.sleep(60)
      
