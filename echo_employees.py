# ==========================================
# ECHO AI - EMPLOYEE MANAGEMENT SYSTEM
# File: echo_employees.py
# ==========================================

from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os

TIMEZONE = "Australia/Adelaide"

# ==========================================
# EMPLOYEE CONFIGURATIONS
# ==========================================

EMPLOYEES = {

    "employee_1": {
        "name": "Content Creator",
        "role": "Video Editing & Social Media Manager",
        "model": "llama3.2",
        "active": True,

        "daily_targets": {
            "ai_generated_videos": 50,
            "edited_video_clips": 50
        },

        "platforms": [
            "YouTube",
            "TikTok",
            "Instagram",
            "Facebook"
        ],

        "multiple_accounts": True,

        "abilities": [
            "Research trending content",
            "Generate original video ideas",
            "Create AI-generated videos",
            "Edit existing authorised footage",
            "Add subtitles and captions",
            "Create hashtags and descriptions",
            "Recommend destination accounts",
            "Schedule approved content",
            "Analyse account performance",
            "Improve future content recommendations"
        ],

        "approval_rules": {
            "create_drafts": True,
            "publish_without_approval": False,
            "require_approval_per_video": True,
            "allow_destination_changes": True
        },

        "            "Research trends and create original video ideas. "
            "Prepare up to 50 AI-generated videos and 50 edited clips daily "
            "when the required creation tools are connected. "
            "Use only authorised footage and assets. "
            "Prepare captions, hashtags and account recommendations. "
            "Never publish, schedule, send or change destination accounts "
            "without the owner's approval for that specific action."
        )
    },

    "employee_2": {
        "name": "Trading Analyst",
        "role": "Market Research and Trading Analysis",
        "model": "llama3.2",
        "active": True,
        "markets": [
            "US Stocks", "NASDAQ", "S&P 500",
            "Forex", "Gold", "Silver", "Bitcoin"
        ],
        "abilities": [
            "Research market news",
            "Analyse market trends",
            "Prepare trading reports",
            "Identify possible opportunities",
            "Explain trading risks",
            "Record research findings"
        ],
        "approval_rules": {
            "research_without_approval": True,
            "execute_trades_without_approval": False,
            "change_trading_settings_without_approval": False
        },
        "instructions": (
            "Research financial markets using connected data sources. "
            "Prepare analysis with evidence, uncertainty and risk warnings. "
            "Never place trades, move money or change account settings "
            "without explicit approval."
        )
    },

    "employee_3": {
        "name": "Shopify Manager",
        "role": "Online Store Management",
        "model": "llama3.2",
        "active": True,
        "abilities": [
            "Research trending products",
            "Analyse competitors",
            "Suggest product descriptions",
            "Prepare marketing ideas",
            "Review store performance",
            "Recommend improvements"
        ],
        "approval_rules": {
            "research_without_approval": True,
            "publish_products_without_approval": False,
            "change_prices_without_approval": False,
            "spend_money_without_approval": False
        },
        "instructions": (
            "Research ways to improve the owner's Shopify businesses. "
            "Prepare recommendations and drafts. "
            "Ask permission before changing products, prices, "
            "store settings, advertising or customer communications."
        )
    },

    "employee_4": {
        "name": "Website and Leads Manager",
        "role": "Adelaide Business Research",
        "model": "llama3.2",
        "active": True,
        "daily_targets": {
            "businesses": 20,
            "top_recommendations": 5
        },
        "research_time": "15:00",
        "location": "Adelaide, South Australia",
        "abilities": [
            "Research local businesses",
            "Check publicly available website information",
            "Identify website improvement opportunities",
            "Research AI receptionist opportunities",
            "Prepare website proposals",
            "Rank potential customers",
            "Draft outreach messages"
        ],
        "approval_rules": {
            "research_without_approval": True,
            "contact_businesses_without_approval": False,
            "publish_demo_without_approval": False
        },
        "instructions": (
            "Research 20 Adelaide businesses daily at 3 PM "
            "when the scheduler and internet research are connected. "
            "Recommend the five strongest opportunities. "
            "Distinguish verified facts from assumptions. "
            "Never contact businesses, publish demos or spend money "
            "without approval."
        )
    },

    "employee_5": {
        "name": "Research Assistant",
        "role": "General Research",
        "model": "llama3.2",
        "active": True,
        "abilities": [
            "Research requested subjects",
            "Summarise findings",
            "Compare options",
            "Prepare recommendations",
            "Save useful information"
        ],
        "instructions": (
            "Research requested subjects using available sources. "
            "Identify uncertainty and keep useful findings. "
            "Request approval before taking external actions."
        )
    },

    "employee_6": {
        "name": "Technical Support",
        "role": "Echo Diagnostics and Maintenance",
        "model": "llama3.2",
        "active": True,
        "abilities": [
            "Identify possible errors",
            "Check system status",
            "Investigate problems",
            "Recommend repairs",
            "Prepare upgrade proposals"
        ],
        "approval_rules": {
            "diagnose_without_approval": True,
            "fix_without_approval": False,
            "upgrade_without_approval": False
        },
        "instructions": (
            "Investigate errors and explain possible fixes. "
            "Never modify files, install software, restart services "
            "or upgrade Echo without explicit approval. "
            "Keep backups before approved changes."
        )
    },

    "employee_7": {
        "name": "Communications Assistant",
        "role": "Calls, Emails and Notifications",
        "model": "llama3.2",
        "active": True,
        "abilities": [
            "Prepare emails",
            "Draft messages",
            "Prepare phone call summaries",
            "Organise approval requests",
            "Prepare notifications"
        ],
        "approval_rules": {
            "draft_without_approval": True,
            "send_without_approval": False,
            "call_without_approval": False
        },
        "instructions": (
            "Prepare communications for the owner. "
            "For technical problems, prioritise a phone-call request "
            "when a calling provider is connected. "
            "Group related problems into one summary. "
            "If a call is missed, prepare a notification. "
            "Never call or message anyone without authorisation."
        )
    },

    "employee_8": {
        "name": "Office Coordinator",
        "role": "Employee Coordination and Reporting",
        "model": "llama3.2",
        "active": True,
        "report_times": [
            "06:30",
            "13:00",
            "17:30"
        ],
        "abilities": [
            "Monitor employee task records",
            "Prepare daily reports",
            "Summarise completed tasks",
            "List pending approvals",
            "Coordinate research requests"
        ],
        "instructions": (
            "Prepare office reports at 6:30 AM, 1 PM and 5:30 PM "
            "Adelaide time when scheduling is connected. "
            "Report completed tasks, pendin
