# ==========================================
# ECHO AI - DAILY SCHEDULER
# File: echo_scheduler.py
# ==========================================

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from echo_tasks import EMPLOYEE_ROLES, load_tasks, save_tasks
from echo_telegram import send_report, send_alert, send_message
import echo_leads
import echo_trading
import echo_business
import echo_memory
import echo_growth
import echo_opusclip
import echo_brain
import echo_log
import echo_backup
import echo_health
import echo_ceo
import threading

TIMEZONE = ZoneInfo("Australia/Adelaide")

# Files live next to this script so Echo works from any starting folder.
ROOT = Path(__file__).resolve().parent
SCHEDULE_FILE = ROOT / "echo_schedule.json"

# Unreviewed tasks older than this are marked "expired" so reports stay readable.
EXPIRE_AFTER_DAYS = 7

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


def queue_tasks(items):
    """Queue (employee, description) pairs in one load/save, skipping duplicates."""
    tasks = load_tasks()
    existing = {task["description"] for task in tasks.values()}
    added = 0
    for employee, description in items:
        if description in existing:
            continue
        task_id = str(uuid.uuid4())
        tasks[task_id] = {
            "id": task_id,
            "employee_id": employee,
            "employee": EMPLOYEE_ROLES[employee],
            "description": description,
            "status": "waiting_for_approval",
            "created": datetime.now(timezone.utc).isoformat(),
        }
        existing.add(description)
        added += 1
    if added:
        save_tasks(tasks)
    return added


def expire_old_tasks():
    tasks = load_tasks()
    cutoff = datetime.now(timezone.utc) - timedelta(days=EXPIRE_AFTER_DAYS)
    changed = 0
    for task in tasks.values():
        if task.get("status") != "waiting_for_approval":
            continue
        try:
            created = datetime.fromisoformat(task["created"])
        except (KeyError, ValueError):
            continue
        if created < cutoff:
            task["status"] = "expired"
            changed += 1
    if changed:
        save_tasks(tasks)
    return changed


# ==========================================
# EMPLOYEE 1 - CONTENT CREATOR
# ==========================================

def schedule_content():
    date = today()
    items = [
        ("employee_1",
         f"{date}: AI video idea {number}. "
         "Prepare an original video concept. "
         "Suggest the best social media account. "
         "Wait for approval.")
        for number in range(1, DAILY_TARGETS["ai_generated_videos"] + 1)
    ] + [
        ("employee_1",
         f"{date}: Edited clip idea {number}. "
         "Identify suitable authorised footage. "
         "Prepare an editing plan. "
         "Wait for approval.")
        for number in range(1, DAILY_TARGETS["edited_video_clips"] + 1)
    ]
    queue_tasks(items)


# ==========================================
# EMPLOYEE 4 - BUSINESS LEADS
# ==========================================

def schedule_leads():
    date = today()

    queue_tasks([(
        "employee_4",
        f"{date}: Research up to 20 businesses "
        "that may need websites or AI receptionists. "
        "Verify their public business information. "
        "Rank the best 5 opportunities. "
        "Do not build demos or contact businesses "
        "without approval."
    )])


def format_leads(result):
    lines = [f"ECHO LEADS - {result['date']}",
             f"Researched {result['researched']} businesses. Top {len(result['top_leads'])}:", ""]
    for number, lead in enumerate(result["top_leads"], 1):
        lines.append(f"{number}. {lead['name']} (score {lead['score']})")
        if lead["reasons"]:
            lines.append("   " + "; ".join(lead["reasons"]))
        if lead["phone"]:
            lines.append("   " + lead["phone"])
    lines += ["", result["note"]]
    return "\n".join(lines)


def run_trade_scan(schedule):
    """Each evening, text the best trade idea; nothing is placed unless you tap Place trade."""
    date = today()
    if current_time().strftime("%H:%M") < echo_trading.SCAN_TIME or schedule.get("last_trade_scan") == date:
        return
    if current_time().weekday() >= 5:  # US market closed weekends (Sat/Sun evenings in Adelaide)
        return
    schedule["last_trade_scan"] = date
    save_schedule(schedule)
    try:
        print("Trade scan:", echo_trading.send_idea_to_phone()[:120])
    except Exception as exc:
        print("Trade scan failed:", exc)
        echo_log.error("Trade scan failed", exc)


_last_trench_check = [0.0]


def run_trench_watch():
    """Every 5 minutes, text a close alert when a Trench trade hits its stop or target."""
    if time.time() - _last_trench_check[0] < 300:
        return
    _last_trench_check[0] = time.time()
    try:
        for alert in echo_trading.check_trench_trades():
            echo_trading._telegram_text(alert)
        echo_trading.check_paper_exits()  # practice account: sell at the stop or target
    except Exception as exc:
        print("Trench watch failed:", exc)
        echo_log.error("Trench watch failed", exc)


CEO_TIME = "18:00"


def run_ceo_summary(schedule):
    """6 PM: the CEO's daily business summary to your phone."""
    date = today()
    if current_time().strftime("%H:%M") < CEO_TIME or schedule.get("last_ceo") == date:
        return
    schedule["last_ceo"] = date
    save_schedule(schedule)
    try:
        send_message(echo_business.ceo_summary())
    except Exception as exc:
        print("CEO summary failed:", exc)
        echo_log.error("CEO summary failed", exc)


def run_ops_check(schedule):
    """Operations Manager: alert once a day if a part of Echo has gone quiet."""
    echo_business.heartbeat("scheduler")
    status = echo_business.status_text()
    problems = [l for l in status.splitlines() if l.startswith("🔴")]
    key = "last_ops_alert"
    if problems and schedule.get(key) != today():
        schedule[key] = today()
        save_schedule(schedule)
        send_alert("Operations Manager: something needs attention\n" + "\n".join(problems))


_last_call_check = [0.0]


def run_phone_checkins(schedule):
    """Every 5 minutes: if an employee needs you (trade approval, update, urgent customer,
    something broken, follow-ups), Echo rings you - once per new need, never 9 PM-8 AM."""
    if time.time() - _last_call_check[0] < 300:
        return
    _last_call_check[0] = time.time()
    try:
        import echo_phone
        needs = echo_phone.briefing()
        new = [n for n in needs if n not in schedule.get("called_about", [])]
        if not new or not echo_phone.may_call():
            return
        approval = None
        if any("trade idea" in n for n in new):
            approval = "trade"
        elif any("update waiting" in n for n in new):
            approval = "update"
        opening = "Hi, it's Echo. " + "; ".join(new[:3]) + "."
        if approval == "trade":
            opening += " Want me to go ahead with the trade? Just say yes or no."
        elif approval == "update":
            opening += " Should I install the update? Yes or no."
        else:
            opening += " Anything you'd like me to do?"
        result = echo_phone.call_me(opening, topic="Employees need: " + "; ".join(needs), approval=approval)
        print("Phone check-in:", result)
        if result.startswith("Calling"):
            schedule["called_about"] = (schedule.get("called_about", []) + new)[-40:]
            save_schedule(schedule)
    except Exception as exc:
        print("Phone check-in failed:", exc)
        echo_log.error("Phone check-in failed", exc)


_last_memory_tidy = [0.0]


_background = {"thread": None}


def run_in_background(name, job):
    """Run a slow AI job (research, summaries) without holding up the 60-second loop, one at a time,
    and only while the owner isn't talking to Echo (so chats and phone calls get the AI first)."""
    t = _background["thread"]
    if (t and t.is_alive()) or echo_brain.owner_active():
        return False

    def runner():
        try:
            job()
        except Exception as error:
            print(f"{name} skipped:", error)
            echo_log.error(name, error)
    _background["thread"] = threading.Thread(target=runner, name=name, daemon=True)
    _background["thread"].start()
    return True


def run_memory_summaries():
    """Every 30 minutes, turn finished chats into short memories (local model, free)."""
    if time.time() - _last_memory_tidy[0] < 1800:
        return
    if not run_in_background("Memory summary", _summarise_chats):
        return
    _last_memory_tidy[0] = time.time()


def _summarise_chats():
    try:
        done = echo_memory.summarise_finished_chats()
        if done:
            print(f"Echo memory: summarised {done} finished chat(s).")
    except Exception as error:
        print("Memory summary skipped:", error)
        echo_log.error("Memory summary skipped", error)


def run_growth():
    """Echo's own research (every 90 min, 7 AM-10 PM) and the evening review of how it talks."""
    run_in_background("Growth step", lambda: echo_growth.tick(current_time(), notify=send_message))


_last_opus_check = [0.0]


def run_opusclip_check():
    """Every 5 minutes: tell the owner when OpusClip has finished making clips."""
    if time.time() - _last_opus_check[0] < 300:
        return
    _last_opus_check[0] = time.time()
    try:
        echo_opusclip.check_projects(notify=send_message)
    except Exception as error:
        print("OpusClip check skipped:", error)
        echo_log.error("OpusClip check skipped", error)


def run_error_report(schedule):
    """Each morning from 8 AM: if anything went wrong in the last day, text a short list."""
    if current_time().hour < 8:
        return
    msg = echo_log.since_last_report(schedule)
    save_schedule(schedule)
    if msg:
        send_message(msg)


def run_backup():
    """Nightly backup of memory, records and settings (not keys) to OneDrive/Documents."""
    if echo_backup.due(current_time().replace(tzinfo=None)):
        def job():
            path, text = echo_backup.backup_now()
            print(text)
        run_in_background("Backup", job)


def run_weekly_health(schedule):
    """Every Sunday from 10 AM: Echo checks every part of itself and texts the result."""
    now = current_time()
    if now.weekday() != 6 or now.hour < 10 or schedule.get("last_health") == today():
        return
    schedule["last_health"] = today()
    save_schedule(schedule)
    run_in_background("Health check", lambda: send_message(echo_health.report()))


def run_ceo_plan(schedule):
    """The CEO makes a weekly plan from your goals (Mondays, or when there isn't one), and from
    8:30 AM each day sends today's top 3."""
    now = current_time()
    if now.hour >= 7 and echo_ceo.needs_new_plan(now.date()) and schedule.get("last_ceo_plan_try") != today():
        if run_in_background("CEO plan", lambda: send_message(echo_ceo.make_plan(today=now.date()))):
            schedule["last_ceo_plan_try"] = today()
            save_schedule(schedule)
        return
    if now.strftime("%H:%M") >= "08:30" and schedule.get("last_morning_plan") != today():
        schedule["last_morning_plan"] = today()
        save_schedule(schedule)
        text = echo_ceo.morning_text()
        if text:
            send_message(text)


def run_lead_research(schedule):
    """At 3 PM, run real lead research if a Google Places key is set."""
    date = today()
    due = current_time().hour >= echo_leads.REPORT_HOUR
    if not due or schedule.get("last_leads") == date:
        return
    schedule["last_leads"] = date
    save_schedule(schedule)
    if not echo_leads.API_KEY:
        print("Lead research skipped: no Google Places key set.")
        return
    result = echo_leads.research_leads()
    print(f"Lead research done: {result['researched']} businesses.")
    send_message(echo_leads.summary(result))


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
            "Video tasks are plans waiting for your "
            "approval; video tools are not connected, "
            "so no videos were made automatically. "
            "Lead research finds 20 new businesses at 3 PM "
            "when a Google Places key is set."
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
        expired = expire_old_tasks()
        if expired:
            print(f"Marked {expired} old unreviewed tasks as expired.")

    run_lead_research(schedule)
    run_trade_scan(schedule)
    run_trench_watch()
    run_ceo_summary(schedule)
    run_ops_check(schedule)
    run_phone_checkins(schedule)
    run_memory_summaries()
    run_growth()
    run_opusclip_check()
    run_error_report(schedule)
    run_backup()
    run_weekly_health(schedule)
    run_ceo_plan(schedule)

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
    echo_log.install()
    print("ECHO AI SCHEDULER STARTED")
    print("Timezone: Australia/Adelaide")
    print("Reports: 6:30 AM, 1 PM, 5:30 PM")
    print("Approval required for all actions")

    while True:
        try:
            run_daily_schedule()
        except Exception as error:
            print("Scheduler error:", error)
            echo_log.error("Scheduler error", error)
            alert_once("Scheduler error: " + str(error))

        time.sleep(60)
