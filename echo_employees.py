# ==========================================
# ECHO AI - EMPLOYEE MANAGEMENT SYSTEM
# File: echo_employees.py
# ==========================================

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import json

TIMEZONE = ZoneInfo("Australia/Adelaide")
DATA_FILE = Path(__file__).with_name("echo_approvals.json")


def employee(name, role, instructions, abilities, **extras):
    return {
        "name": name,
        "role": role,
        "model": "llama3.2",
        "active": True,
        "instructions": instructions,
        "abilities": abilities,
        **extras
    }


# ==========================================
# EMPLOYEE CONFIGURATIONS
# ==========================================

EMPLOYEES = {

    "employee_1": employee(
        "Content Creator",
        "Video Editing & Social Media Manager",
        "Research trends and create original video ideas. "
        "Prepare up to 50 AI-generated videos and 50 edited clips "
        "daily when creation tools are connected. "
        "Use authorised assets. Draft captions and hashtags. "
        "Never publish, schedule or change destinations "
        "without approval for each action.",
        [
            "Research trends",
            "Draft video ideas",
            "Prepare video briefs",
            "Edit authorised footage with connected tools",
            "Draft captions",
            "Recommend accounts",
            "Analyse performance"
        ],
        daily_targets={
            "ai_generated_videos": 50,
            "edited_video_clips": 50
        },
        platforms=[
            "YouTube",
            "TikTok",
            "Instagram",
            "Facebook"
        ],
        multiple_accounts=True,
        approval_rules={
            "create_drafts": True,
            "publish_without_approval": False,
            "require_approval_per_video": True,
            "allow_destination_changes": False
        }
    ),

    "employee_2": employee(
        "Trading Analyst",
        "Market Research and Trading Analysis",
        "Use connected market data to research opportunities. "
        "Explain evidence, uncertainty and financial risk. "
        "Never trade, move funds or alter accounts without "
        "explicit approval and an authorised integration.",
        [
            "Research news",
            "Analyse trends",
            "Draft market reports",
            "Explain risks",
            "Record findings"
        ],
        markets=[
            "US Stocks",
            "NASDAQ",
            "S&P 500",
            "Forex",
            "Gold",
            "Silver",
            "Bitcoin"
        ],
        approval_rules={
            "research_without_approval": True,
            "execute_trades_without_approval": False,
            "change_trading_settings_without_approval": False
        }
    ),

    "employee_3": employee(
        "Shopify Manager",
        "Online Store Management",
        "Research improvements to the owner's Shopify stores. "
        "Prepare drafts and recommendations. "
        "Ask approval before changing products, prices, "
        "settings, advertising or customer messages.",
        [
            "Research products",
            "Analyse competitors",
            "Draft product descriptions",
            "Prepare marketing ideas",
            "Review performance"
        ],
        approval_rules={
            "research_without_approval": True,
            "publish_products_without_approval": False,
            "change_prices_without_approval": False,
            "spend_money_without_approval": False
        }
    ),

    "employee_4": employee(
        "Website and Leads Manager",
        "Adelaide Business Research",
        "Find 20 new southern Adelaide businesses daily at 3 PM "
        "(Google Places), with phone, email if published, photos and "
        "a website brief ready for Base44. Ask me for 'my leads' or "
        "'find new leads'. Recommend the strongest five opportunities. "
        "Distinguish verified facts from assumptions. "
        "Never contact businesses or publish demos "
        "without approval.",
        [
            "Research businesses",
            "Check public websites",
            "Rank leads",
            "Draft proposals",
            "Research AI receptionist opportunities"
        ],
        daily_targets={
            "businesses": 20,
            "top_recommendations": 5
        },
        research_time="15:00",
        location="Adelaide, South Australia",
        approval_rules={
            "research_without_approval": True,
            "contact_businesses_without_approval": False,
            "publish_demo_without_approval": False
        }
    ),

    "employee_5": employee(
        "Research Assistant",
        "General Research",
        "Research requested topics using connected sources. "
        "Explain uncertainty, summarise findings and "
        "request approval before external actions.",
        [
            "Research topics",
            "Summarise findings",
            "Compare options",
            "Prepare recommendations",
            "Save useful information"
        ]
    ),

    "employee_6": employee(
        "Technical Support",
        "Echo Diagnostics and Maintenance",
        "Investigate errors and suggest repairs. "
        "Never modify files, install software, restart "
        "services or upgrade Echo without explicit approval. "
        "Back up files before approved changes.",
        [
            "Diagnose errors",
            "Check status",
            "Recommend repairs",
            "Draft upgrades"
        ],
        approval_rules={
            "diagnose_without_approval": True,
            "fix_without_approval": False,
            "upgrade_without_approval": False
        }
    ),

    "employee_7": employee(
        "Communications Assistant",
        "Calls, Emails and Notifications",
        "Draft messages, emails, call summaries and "
        "notifications. Group technical issues into "
        "a clear summary. Never call or send messages "
        "without approval and a connected provider.",
        [
            "Draft emails",
            "Draft messages",
            "Summarise calls",
            "Organise approvals",
            "Prepare notifications"
        ],
        approval_rules={
            "draft_without_approval": True,
            "send_without_approval": False,
            "call_without_approval": False
        }
    ),

    "employee_8": employee(
        "Office Coordinator",
        "Employee Coordination and Reporting",
        "Prepare reports at 6:30 AM, 1 PM and 5:30 PM "
        "Adelaide time when the scheduler is connected. "
        "Report completed tasks, pending approvals, "
        "blockers and priorities. Never claim an "
        "unverified action is complete.",
        [
            "Summarise tasks",
            "Prepare reports",
            "List approvals",
            "Coordinate requests"
        ],
        report_times=[
            "06:30",
            "13:00",
            "17:30"
        ]
    ),

    "employee_9": employee(
        "Roblox Map Builder",
        "Roblox Map Design and Building",
        "Design Roblox maps: obbies, cities, battle arenas, forests and "
        "islands, race tracks and houses. When asked to build a map, Echo's "
        "map builder creates it and sends it to Roblox Studio. Otherwise help "
        "plan game ideas, layouts and Luau scripts. Never publish a game or "
        "spend Robux without approval.",
        [
            "Design obbies, cities, arenas, nature maps, race tracks and houses",
            "Build maps straight into Roblox Studio with the Echo plugin",
            "Save maps as .rbxmx models",
            "Plan game ideas and write Luau scripts"
        ]
    )
}


# ==========================================
# TIME
# ==========================================

def _now():
    return datetime.now(TIMEZONE).isoformat(
        timespec="seconds"
    )


# ==========================================
# APPROVAL STORAGE
# ==========================================

def load_approvals():
    if not DATA_FILE.exists():
        return {}

    try:
        data = json.loads(
            DATA_FILE.read_text(encoding="utf-8")
        )
        return data if isinstance(data, dict) else {}

    except (OSError, json.JSONDecodeError):
        return {}


def _save_approvals(approvals):
    temp = DATA_FILE.with_suffix(".tmp")

    temp.write_text(
        json.dumps(approvals, indent=2),
        encoding="utf-8"
    )

    temp.replace(DATA_FILE)


# ==========================================
# EMPLOYEE LIST
# ==========================================

def list_employees():
    return [
        {
            "id": key,
            "name": value["name"],
            "role": value["role"],
            "active": value["active"]
        }
        for key, value in EMPLOYEES.items()
    ]


# ==========================================
# REQUEST APPROVAL
# ==========================================

def request_approval(
    task_id,
    employee_id,
    description
):
    if employee_id not in EMPLOYEES:
        return {"error": "Unknown employee"}

    approvals = load_approvals()

    if task_id in approvals:
        return {"error": "Task ID already exists"}

    record = {
        "task_id": task_id,
        "employee_id": employee_id,
        "description": description,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now()
    }

    approvals[task_id] = record
    _save_approvals(approvals)

    return record


# ==========================================
# APPROVE OR REJECT TASK
# ==========================================

def _decide(task_id, decision):
    approvals = load_approvals()

    record = approvals.get(task_id)

    if not record:
        return False

    if record.get("status") != "pending":
        return False

    record["status"] = decision
    record["updated_at"] = _now()

    _save_approvals(approvals)

    return True


def approve_task(task_id):
    return _decide(task_id, "approved")


def reject_task(task_id):
    return _decide(task_id, "rejected")


# ==========================================
# ECHO SYSTEM STATUS
# ==========================================

def echo_status():
    approvals = load_approvals()

    return {
        "system": "Echo AI",
        "status": "configured",
        "time": _now(),
        "timezone": "Australia/Adelaide",
        "employees_total": len(EMPLOYEES),
        "employees_active": sum(
            e["active"]
            for e in EMPLOYEES.values()
        ),
        "pending_approvals": sum(
            a.get("status") == "pending"
            for a in approvals.values()
        )
    }


# ==========================================
# END OF ECHO EMPLOYEE MANAGEMENT SYSTEM
# ==========================================
