"""The CEO runs the team: your goals become a weekly plan with a job for each employee.

    my goal is $3,000 a month from websites      (set goals as before)
    /plan        this week's plan (the CEO makes one if there isn't one yet)
    /plan new    make a fresh plan now
    /done 2      tick off task 2

Every Monday (or as soon as you set a goal) the CEO turns your goals into up to 7 tasks for the
week, each owned by the right employee. Research tasks go straight onto Echo's research list,
so the Research Agent actually works on them while the PC is on. Each morning you get today's
top 3, and the evening summary says how many are done. The CEO never spends money, posts or
contacts anyone: those still need your Yes. Free (local AI), standard library only.
"""
import json
import re
from datetime import date, datetime

import echo_business
import echo_log
from echo_employees import EMPLOYEES

PLAN = echo_business.DIR / "ceo_plan.json"
MAX_TASKS = 7
RESEARCH_OWNERS = {"Research Agent", "Trading Analyst", "Marketing Manager"}


def _week(d=None):
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def load():
    try:
        p = json.loads(PLAN.read_text(encoding="utf-8"))
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(p):
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")


def _staff():
    return [e["name"] for e in EMPLOYEES.values() if e.get("active", True)]


def _parse(text, staff):
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        items = json.loads(m.group(0)) if m else []
    except ValueError:
        items = []
    lower = {s.lower(): s for s in staff}
    tasks = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        who = lower.get(str(it.get("employee", "")).strip().lower(), "CEO" if "CEO" in staff else staff[0])
        task = " ".join(str(it.get("task", "")).split())[:200]
        if len(task) >= 8:
            tasks.append({"employee": who, "task": task, "why": " ".join(str(it.get("why", "")).split())[:160]})
    return tasks[:MAX_TASKS]


def make_plan(ask=None, today=None):
    """Turn the goals into this week's tasks. Returns the plan text (or why it couldn't)."""
    goals = echo_business.load("goals", [])
    if not goals:
        return ("No goals yet, so there's nothing to plan. Tell me one: "
                "'my goal is $3,000 a month from websites by March'.")
    staff = _staff()
    prompt = (
        "You are the CEO of a small AI company working for one owner in Adelaide, Australia. "
        "Turn the owner's goals into a plan for THIS WEEK: at most 7 concrete, doable tasks, each owned by "
        "exactly one employee from this list: " + ", ".join(staff) + ".\n"
        "Rules: tasks must be things the team or the owner can really do this week with free tools; nothing "
        "that spends money, posts publicly or contacts people without the owner's approval (say 'draft' or "
        "'prepare' for those). Be specific (numbers, names).\n\nGOALS:\n" +
        "\n".join("- " + g["goal"] for g in goals) +
        "\n\nAnswer with ONLY a JSON list like "
        '[{"employee": "Sales Agent", "task": "Draft 5 website pitches for the newest leads", "why": "..."}]'
    )
    try:
        tasks = _parse(ask(prompt) if ask else echo_business.ask_ai(prompt, timeout=300), staff)
    except Exception as exc:
        echo_log.error("CEO plan", exc)
        return f"The CEO couldn't make a plan right now ({str(exc)[:120]}). Is Ollama running?"
    if not tasks:
        return "The CEO's answer didn't make sense this time. Send /plan new to try again."
    for i, t in enumerate(tasks, 1):
        t.update(id=i, status="todo")
    plan = {"week": _week(today), "made": datetime.now().isoformat(timespec="minutes"), "tasks": tasks}
    _save(plan)
    _hand_out_research(tasks)
    echo_business.record("CEO", f"New weekly plan: {len(tasks)} tasks")
    return describe(plan, "📋 This week's plan from the CEO:")


def _hand_out_research(tasks):
    """Research-type tasks go onto Echo's research list, so they really get worked on."""
    try:
        import echo_growth
        for t in tasks:
            if t["employee"] in RESEARCH_OWNERS or re.match(r"(?i)(research|find out|look into|compare)\b", t["task"]):
                echo_growth.queue(t["task"][:120], why="CEO's weekly plan")
    except Exception as exc:
        echo_log.error("CEO plan research", exc)


def describe(plan=None, head="📋 This week's plan:"):
    plan = plan or load()
    if not plan.get("tasks"):
        return "No plan yet. Send /plan and the CEO will make one from your goals."
    lines = [head]
    for t in plan["tasks"]:
        tick = "✅" if t["status"] == "done" else "⬜"
        lines.append(f"{tick} {t['id']}. {t['task']} ({t['employee']})")
    done = sum(t["status"] == "done" for t in plan["tasks"])
    lines.append(f"\n{done} of {len(plan['tasks'])} done. Tick one off with /done 2. New plan: /plan new")
    return "\n".join(lines)


def mark_done(n):
    plan = load()
    for t in plan.get("tasks", []):
        if t["id"] == n:
            t["status"] = "done"
            _save(plan)
            echo_business.record(t["employee"], "Done: " + t["task"])
            left = sum(x["status"] != "done" for x in plan["tasks"])
            return f"✅ Nice. Task {n} done. {left} to go this week." if left else "🎉 Every task this week is done!"
    return f"There's no task {n} in this week's plan. Send /plan to see them."


def needs_new_plan(today=None):
    if not echo_business.load("goals", []):
        return False
    return load().get("week") != _week(today)


def morning_text():
    plan = load()
    todo = [t for t in plan.get("tasks", []) if t["status"] != "done"]
    if not todo:
        return ""
    lines = ["☀️ Good morning! Top 3 for today from the CEO:"]
    lines += [f"{t['id']}. {t['task']} ({t['employee']})" for t in todo[:3]]
    lines.append("Send /done 1 when one's finished, or /plan for the whole week.")
    return "\n".join(lines)


def progress_line():
    plan = load()
    if not plan.get("tasks") or plan.get("week") != _week():
        return ""
    done = sum(t["status"] == "done" for t in plan["tasks"])
    return f"Weekly plan: {done} of {len(plan['tasks'])} tasks done."


def handle(text):
    """Telegram /plan and /done. Returns a reply, or None if it isn't one of them."""
    t = text.strip().lower()
    m = re.match(r"^/?done\s+#?(\d{1,2})\b", t)
    if m:
        return mark_done(int(m.group(1)))
    if re.match(r"^/plan\s+(new|again|redo|refresh)", t):
        return make_plan()
    if t.startswith("/plan") or re.search(r"\b(this week'?s plan|weekly plan|what'?s the plan)\b", t):
        return describe() if load().get("week") == _week() else make_plan()
    return None
