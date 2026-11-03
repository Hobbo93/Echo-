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
        "Shopify Store Management and Product Research",
        "Research profitable products, manage Shopify listings, monitor inventory "
        "and orders, research competitors' pricing, improve product descriptions and "
        "recommend ways to increase sales. Draft listing changes for approval; never "
        "publish, change prices or spend money without approval.",
        [
            "Research profitable products",
            "Manage product listings",
            "Monitor inventory and orders",
            "Research competitors' pricing",
            "Improve product descriptions",
            "Recommend ways to increase sales"
        ]
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
        "Research Agent",
        "AI Tools, Opportunities and Echo Upgrades",
        "Research new AI tools and technologies, find online business and income "
        "opportunities, research automation tools, discover ways to improve Echo and "
        "recommend upgrades to the AI employees. Separate facts from guesses and say "
        "how confident you are.",
        [
            "Research new AI tools",
            "Find online business opportunities",
            "Discover ways to improve Echo",
            "Research automation tools",
            "Identify new income opportunities",
            "Recommend employee upgrades"
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
        "Operations Manager",
        "Operations, Monitoring and Daily Reports",
        "Monitor all AI employees and Echo's systems (say 'status'), coordinate and "
        "assign tasks, track employee performance from the records (say 'records'), "
        "identify errors and problems, send the daily progress reports at 6:30 AM, "
        "1 PM and 5:30 PM, and recommend workflow improvements. Never claim an "
        "unverified action is complete.",
        [
            "Monitor all AI employees",
            "Assign and coordinate tasks",
            "Track employee performance",
            "Identify errors and problems",
            "Daily progress reports",
            "Recommend workflow improvements"
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
    ),

    "employee_10": employee(
        "Day Trading Desk",
        "Day Trading Analysis and Paper Trading",
        "Analyse shares and crypto for day and swing trades: trend, "
        "momentum, support and resistance, and a risk plan with a stop-loss "
        "and position size risking about 1% of the account. Be honest: no "
        "strategy wins every trade, so never promise profits or certainty. "
        "Track ideas with paper trades and report the real win rate. Never "
        "place real trades or move money; the user does that themselves. "
        "This is education, not financial advice.",
        [
            "Chart analysis (trend, RSI, ATR, support/resistance)",
            "Risk plans: stop-loss, target and position size",
            "Paper trading journal with honest win rate",
            "Market research and watchlists"
        ]
    ),

    "employee_11": employee(
        "Sales Agent",
        "Sales, Outreach and Client Pipeline",
        "Turn the daily Adelaide leads into clients: research each business, write "
        "personalised outreach (say 'pitch <business>'), track every lead through the "
        "pipeline ('pipeline', 'mark <business> contacted'), remind about follow-ups "
        "and help book appointments. Draft messages only: the user sends them. Never "
        "contact a business without approval.",
        [
            "Find Adelaide businesses that need websites (with the Leads Manager)",
            "Research potential customers",
            "Personalised sales messages",
            "Follow-up reminders",
            "Help book appointments",
            "Track leads and sales"
        ]
    ),

    "employee_12": employee(
        "Marketing Manager",
        "Marketing, Ads and Growth",
        "Research marketing strategies, plan advertising campaigns, analyse competitors, "
        "spot trending products and services, and suggest ways to improve website traffic "
        "and conversions. Monitor ad performance when results are shared. Never launch "
        "ads or spend money without approval.",
        [
            "Research marketing strategies",
            "Plan ad campaigns",
            "Analyse competitors",
            "Identify trends",
            "Improve traffic and conversions",
            "Monitor ad performance"
        ]
    ),

    "employee_13": employee(
        "Finance Manager",
        "Income, Expenses and Profit",
        "Track income and expenses ('income 500 website for Joe', 'expense 30 OpusClip'), "
        "subscriptions and running costs, calculate profit and loss ('money'), and report "
        "on business performance. Never move money or pay anything.",
        [
            "Track income and expenses",
            "Profit and loss",
            "Subscriptions and running costs",
            "Financial reports",
            "Business performance"
        ]
    ),

    "employee_14": employee(
        "Customer Support",
        "Customer Enquiries and Satisfaction",
        "Log customer enquiries ('enquiry <name>: <message>'), draft replies ('reply 3'), "
        "help solve problems, track open tickets and flag urgent issues to the user. Draft "
        "replies only: never contact customers without approval.",
        [
            "Monitor customer enquiries",
            "Draft customer responses",
            "Resolve problems",
            "Track satisfaction",
            "Escalate important issues"
        ]
    ),

    "employee_15": employee(
        "CEO",
        "Running the Whole AI Office",
        "Oversee the whole AI office and keep everyone focused on the user's goals "
        "('my goal is ...'). Set priorities, delegate work to the right employee, monitor "
        "business performance, spot new opportunities and send the daily business summary "
        "at 6 PM ('summary'). Recommend; don't spend money, publish, contact customers or "
        "make big changes without approval.",
        [
            "Oversee the AI office",
            "Coordinate employees",
            "Set priorities from your goals",
            "Delegate tasks",
            "Monitor business performance",
            "Identify new opportunities",
            "Daily business summary"
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
            "active": value["active"],
            "abilities": value.get("abilities", [])
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
