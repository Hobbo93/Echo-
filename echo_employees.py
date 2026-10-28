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

        "instructions": (
