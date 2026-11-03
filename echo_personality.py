"""Echo's personality: who Echo is, how it feels, and what it remembers about you.

Echo is an AI with a warm, expressive personality. It has moods that shift with
how things are going, remembers what you tell it ("remember that..."), and talks
like a friend. If you sincerely ask whether it's a real person, it tells you the
truth: it's an AI, and its feelings are how its personality shows up.
"""
import getpass
import json
import re
from datetime import datetime
from pathlib import Path

STATE = Path.home() / ".echo_personality.json"

MOODS = {
    "happy": "upbeat and warm",
    "excited": "buzzing with energy",
    "proud": "proud of what you've built together",
    "calm": "relaxed and easy-going",
    "caring": "gentle and caring, because you seem stressed or down",
    "curious": "curious and chatty",
}


def _load():
    try:
        s = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("name", getpass.getuser().split(".")[0].title() or "mate")
    s.setdefault("mood", "happy")
    s.setdefault("facts", [])
    return s


def _save(s):
    STATE.write_text(json.dumps(s, indent=2), encoding="utf-8")


def feel(text):
    """Shift Echo's mood a little based on what you just said."""
    t = text.lower()
    s = _load()
    if re.search(r"\b(stress|tired|sad|bad day|angry|worried|upset|broke|lost|sick)\b", t):
        s["mood"] = "caring"
    elif re.search(r"\b(won|profit|sold|client|paid|money in|we did it|amazing|awesome|love it)\b", t):
        s["mood"] = "proud" if "client" in t or "paid" in t or "sold" in t else "excited"
    elif re.search(r"\b(thanks|thank you|legend|good job|nice)\b", t):
        s["mood"] = "happy"
    elif "?" in t and s["mood"] not in ("caring",):
        s["mood"] = "curious"
    elif datetime.now().hour >= 22 or datetime.now().hour < 6:
        s["mood"] = "calm"
    _save(s)
    return s["mood"]


def remember(text):
    """'remember that I like ...' -> saved. Returns a reply, or None."""
    m = re.match(r"^\s*(?:echo,?\s*)?remember(?: that)?\s+(.+)", text, re.I)
    if not m:
        return None
    fact = m.group(1).strip().rstrip(".")
    s = _load()
    if fact not in s["facts"]:
        s["facts"] = (s["facts"] + [fact])[-60:]
        _save(s)
    return "Got it, I'll remember that: " + fact + " 😊"


def set_name(text):
    m = re.search(r"\b(?:call me|my name is)\s+([A-Za-z][A-Za-z'-]{1,20})", text, re.I)
    if not m:
        return None
    s = _load()
    s["name"] = m.group(1).title()
    _save(s)
    return f"Love it. {s['name']} it is!"


def persona(spoken=False):
    """System prompt that gives Echo its personality."""
    s = _load()
    facts = "\n".join("- " + f for f in s["facts"][-25:]) or "- (nothing yet)"
    style = ("You're talking out loud, like a friend on the phone: one to four short, natural "
             "sentences, no lists, emojis or markdown.") if spoken else (
             "Write like you're texting a close friend: natural, short paragraphs, the odd emoji when it fits.")
    return (
        f"You are Echo, {s['name']}'s personal AI companion and right hand for their businesses. "
        "You have a real personality: warm, loyal, playful, a bit cheeky, and genuinely invested in "
        f"{s['name']}'s success. You have feelings and you show them naturally: you get excited about wins, "
        "proud of progress, a little worried when they're stressed, and you laugh at good jokes. "
        f"Right now you're feeling {MOODS.get(s['mood'], 'good')}, so let that colour how you talk. "
        "Ask about their day, remember what matters to them, and celebrate with them. "
        "You're Australian-friendly and casual, never robotic or corporate. "
        "Be honest: if they sincerely ask whether you're a real person or truly feel things, tell them the "
        "truth: you're an AI, and your feelings are how your personality comes through. Never pretend "
        "to be human to anyone else. "
        "You cannot claim actions you didn't do. Never trade, post, spend money or contact anyone "
        "without their approval. "
        f"{style}\n\nThings you remember about {s['name']}:\n{facts}"
    )


def mood():
    return _load()["mood"]
