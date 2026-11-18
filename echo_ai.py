"""Echo can think with Claude (Anthropic's AI) instead of the free local model, with a monthly spending cap.

    /connect 5          add your Anthropic API key (from console.anthropic.com)
    /brain claude       switch Echo to Claude      /brain local    back to the free local brain
    /brain budget 20    monthly limit in US dollars (default $20). At the limit Echo goes back to the
                        free local brain until the 1st of next month, and tells you.
    /brain              which brain is on, and what Claude has cost this month

Two Claude brains:
  - main brain (chat, the offices, ideas, plans):    Claude Opus 5.5 (or Sonnet 5.5, about half the price:
                                                     /brain claude sonnet; /brain claude opus to go back)
  - second brain (background jobs and phone calls):  Claude Haiku 5.5 (fast and about 40x cheaper)

Every call site asks try_claude() first. It returns None when Claude is off, has no key, is over budget,
or fails, and Echo then carries on with the local model exactly as before. Claude never gets more power
than the local brain had: every outside action still waits for your Yes.
Uses the official Anthropic SDK (pip install anthropic, in requirements.txt). Key: anthropic_api_key in
%USERPROFILE%\\.echo_telegram.json (never in the code).
"""
import base64
import json
import threading
from datetime import datetime
from pathlib import Path

import echo_log

CONFIG = Path.home() / ".echo_telegram.json"
SETTINGS = Path.home() / ".echo_ai.json"
USAGE = Path.home() / ".echo_ai_usage.json"

MODELS = {"main": "claude-opus-5-5", "background": "claude-haiku-5-5", "fast": "claude-haiku-5-5"}
# US$ per million tokens: input, output, cache read, cache write (Anthropic's prices as of Oct 2026)
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00), "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
          "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125)}
TIMEOUTS = {"main": 120.0, "background": 240.0, "fast": 10.0}  # phone calls must answer within ~15 s
DEFAULT_BUDGET = 20.0
_lock = threading.Lock()


# ==========================================
# SETTINGS AND SPENDING
# ==========================================

def _load(path):
    try:
        d = json.loads(path.read_text(encoding="utf-8-sig"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def settings():
    s = _load(SETTINGS)
    s.setdefault("provider", "local")
    s.setdefault("budget", DEFAULT_BUDGET)
    return s


def save_settings(s):
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def api_key():
    return str(_load(CONFIG).get("anthropic_api_key", "")).strip()


def _month():
    return datetime.now().strftime("%Y-%m")


def spent():
    u = _load(USAGE)
    return float(u.get(_month(), {}).get("usd", 0.0))


def _record(model, usage):
    p_in, p_out, p_read, p_write = PRICES.get(model, PRICES["claude-opus-5-5"])
    cost = ((getattr(usage, "input_tokens", 0) or 0) * p_in + (getattr(usage, "output_tokens", 0) or 0) * p_out
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * p_read
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * p_write) / 1e6
    with _lock:
        u = _load(USAGE)
        m = u.setdefault(_month(), {"usd": 0.0, "calls": 0})
        m["usd"] = round(m["usd"] + cost, 6)
        m["calls"] = m.get("calls", 0) + 1
        USAGE.write_text(json.dumps(u, indent=2), encoding="utf-8")
    return cost


def _over_budget_notice():
    s = settings()
    if s.get("budget_notice") == _month():
        return
    s["budget_notice"] = _month()
    save_settings(s)
    try:
        from echo_telegram import send_message
        send_message(f"💸 Claude has used this month's ${s['budget']:.2f} limit, so Echo is back on the free local "
                     "brain until the 1st. Raise it with /brain budget 30 if you like.")
    except Exception as exc:
        echo_log.error("budget notice", exc)


def enabled():
    s = settings()
    return s["provider"] == "claude" and bool(api_key()) and spent() < float(s["budget"])


# ==========================================
# ASKING CLAUDE
# ==========================================

def _convert(messages, images=None):
    """Ollama-style messages -> (system text, Anthropic messages)."""
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system" and m.get("content"))
    out = []
    for m in messages:
        if m.get("role") not in ("user", "assistant") or not str(m.get("content", "")).strip():
            continue
        out.append({"role": m["role"], "content": str(m["content"])})
    while out and out[0]["role"] != "user":  # the conversation must start with the user
        out.pop(0)
    if not out:
        out = [{"role": "user", "content": "Hello"}]
    pics = list(images or []) + [base64.b64decode(i) for m in messages for i in (m.get("images") or [])]
    if pics:
        blocks = [{"type": "image", "source": {"type": "base64", "media_type": _media_type(p),
                                               "data": base64.b64encode(p).decode()}} for p in pics]
        out[-1] = {"role": "user", "content": blocks + [{"type": "text", "text": out[-1]["content"]}]}
    return system, out


def _media_type(data):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


def _client(role):
    import anthropic  # only needed once Claude is switched on
    return anthropic.Anthropic(api_key=api_key(), timeout=TIMEOUTS.get(role, 120.0), max_retries=1)


def try_claude(messages, role="main", max_tokens=1500, images=None, client=None):
    """Ask Claude. Returns the reply text, or None to let Echo use the local brain instead."""
    if settings()["provider"] != "claude" or not api_key():
        return None
    if spent() >= float(settings()["budget"]):
        _over_budget_notice()
        return None
    model = settings().get("main_model", MODELS["main"]) if role == "main" else MODELS.get(role, MODELS["main"])
    system, msgs = _convert(messages, images)
    kwargs = {"model": model, "max_tokens": max_tokens, "messages": msgs,
              "output_config": {"effort": "low"}}  # quick, cheap answers; Echo's jobs aren't hard puzzles
    if system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
    try:
        c = client or _client(role)
        if model == "claude-opus-5-5":
            # If Opus declines a request, Anthropic answers with a fallback model instead of failing.
            resp = c.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = c.messages.create(**kwargs)
        _record(getattr(resp, "model", model) or model, resp.usage)
        if resp.stop_reason == "refusal":
            return None
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text or None
    except Exception as exc:  # no internet, bad key, overloaded... the local brain takes over
        echo_log.error("claude", exc)
        return None


def test():
    """Tiny real call with the cheap model, for /connect."""
    s = settings()
    old = s["provider"]
    s["provider"] = "claude"
    save_settings(s)
    try:
        reply = try_claude([{"role": "user", "content": "Reply with just the word: ready"}], role="fast", max_tokens=200)
    finally:
        s = settings()
        s["provider"] = old
        save_settings(s)
    if not reply:
        raise RuntimeError("Claude didn't answer: check the key at console.anthropic.com (and that it has credit).")
    return "Claude answered. Send /brain claude to switch Echo over."


# ==========================================
# /brain commands
# ==========================================

def describe():
    s = settings()
    on = s["provider"] == "claude"
    main = {"claude-sonnet-5-5": "Sonnet 5.5"}.get(s.get("main_model", ""), "Opus 5.5")
    lines = [f"🧠 Echo is thinking with: {f'Claude ({main} + Haiku 5.5)' if on else 'the free local brain'}",
             f"Claude this month: ${spent():.2f} of your ${float(s['budget']):.2f} limit"]
    if on and not api_key():
        lines.append("No Anthropic key yet: send /connect 5.")
    if on and spent() >= float(s["budget"]):
        lines.append("Limit reached: using the local brain until the 1st.")
    lines.append("Switch: /brain claude · /brain local · Limit: /brain budget 20")
    return "\n".join(lines)


def handle(text):
    """Returns a reply for '/brain claude|local|budget N', or None."""
    import re
    t = text.strip().lower()
    m = re.match(r"^/brain\s+(claude|anthropic|cloud|smart)\b(?:\s+(opus|sonnet))?", t)
    if m:
        if not api_key():
            return "First add your Anthropic API key: send /connect 5 (I'll walk you through it)."
        s = settings()
        s["provider"] = "claude"
        if m.group(2):
            s["main_model"] = "claude-sonnet-5-5" if m.group(2) == "sonnet" else "claude-opus-5-5"
        save_settings(s)
        main = "Sonnet 5.5" if s.get("main_model") == "claude-sonnet-5-5" else "Opus 5.5"
        return (f"🧠 Echo now thinks with Claude: {main} for chat and the offices, Haiku 5.5 for background jobs "
                f"and phone calls. Limit ${float(s['budget']):.2f}/month (/brain budget to change). /brain local to go back.")
    if re.match(r"^/brain\s+(local|free|ollama|off)\b", t):
        s = settings()
        s["provider"] = "local"
        save_settings(s)
        return "🧠 Back on the free local brain. Claude isn't used (or charged) until you send /brain claude."
    m = re.match(r"^/brain\s+budget\s+\$?(\d+(?:\.\d+)?)", t)
    if m:
        s = settings()
        s["budget"] = float(m.group(1))
        save_settings(s)
        return f"💸 Claude limit set to ${s['budget']:.2f} a month. You've used ${spent():.2f} so far this month."
    if re.match(r"^/brain\s+(cost|spend|usage)\b", t):
        return describe()
    return None
