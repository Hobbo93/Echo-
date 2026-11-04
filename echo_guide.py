"""Guide mode: Echo looks at your PC screen and tells you where to click next. You stay in control.

    /guide connect my shopify store        (or "guide me through ...", "walk me through ...",
                                             "show me how to ...", "show me where to ...")
    next                                     after you've done the step: Echo looks again
    stop                                     end the guide

Each step Echo takes a screenshot, asks the free vision model on your PC what the next
step is, and sends you the screenshot with the instruction. It never clicks or types for
you, and never asks for passwords. For common jobs (connecting Shopify, OpusClip, Gmail)
it also follows Echo's written setup steps, so the advice stays on track.
"""
import re
import time

import echo_photos

TIMEOUT_MIN = 30
MAX_STEPS = 40

_START = re.compile(r"^(?:hey echo,?\s*|echo,?\s*)?(?:can you |could you |please )?"
                    r"(?:/guide|guide me(?: through| to| on)?|walk me through|show me (?:how|where) to|"
                    r"help me (?:find where|get to|find how) to)\s+(?P<goal>.{3,200}?)[.!?]*$", re.I)
_NEXT = re.compile(r"^\s*(next|done|ok(ay)?|did it|done that|what now|now what|next step|got it)[.!]*\s*$", re.I)
_STOP = re.compile(r"^\s*(stop|stop guide|end|finish|finished|cancel|i'?m done|that'?s it|all done)[.!]*\s*$", re.I)

RECIPES = {
    "shopify": (
        "Connect Shopify to Echo: 1) In the browser go to dev.shopify.com/dashboard and log in (the owner logs in "
        "themselves). 2) Click 'Create app', name it Echo. 3) Create a version; under Access > Scopes tick read and "
        "write for products, inventory, orders, discounts, publications, and read_locations; click Release. "
        "4) Click 'Install app' and choose the Furventure store. 5) Open the app's Settings and copy the Client ID "
        "and Client secret. 6) Double-click connect_echo.bat in the Echo folder, say y to Shopify, paste the store "
        "address thedogden-2.myshopify.com, the Client ID and the Client secret."),
    "opus": (
        "Connect OpusClip to Echo: 1) Go to clip.opus.pro and log in. 2) In the dashboard, open 'API key' in the "
        "bottom-left corner and copy it. 3) Double-click connect_echo.bat in the Echo folder, say y to OpusClip "
        "and paste the key."),
    "gmail": (
        "Connect Gmail to Echo: 1) Go to myaccount.google.com/apppasswords (2-step verification must be on). "
        "2) Create an app password named Echo and copy the 16 letters. 3) Double-click connect_echo.bat, say y to "
        "Gmail, enter the Gmail address and paste the app password."),
}
_RECIPE_WORDS = {"shopify": r"shopify|store|furventure", "opus": r"opus ?clip|opus", "gmail": r"g ?mail|e-?mail"}

_state = {}


def _recipe(goal):
    for key, words in _RECIPE_WORDS.items():
        if re.search(words, goal, re.I):
            return RECIPES[key]
    return ""


def active():
    return bool(_state) and time.time() - _state.get("at", 0) < TIMEOUT_MIN * 60


def is_start(text):
    return bool(_START.match((text or "").strip()))


def wants_next(text):
    return active() and bool(_NEXT.match(text or ""))


def wants_stop(text):
    return active() and bool(_STOP.match(text or ""))


def start(text):
    m = _START.match(text.strip())
    goal = m.group("goal").strip() if m else text.strip()
    _state.clear()
    _state.update(goal=goal, steps=[], at=time.time())
    return step()


def stop():
    n = len(_state.get("steps", []))
    _state.clear()
    return f"👍 Guide finished after {n} step{'s' if n != 1 else ''}. Your computer was yours the whole time."


def _prompt():
    done = "\n".join(f"{i}. {s}" for i, s in enumerate(_state["steps"], 1)) or "(none yet)"
    recipe = _recipe(_state["goal"])
    return (
        f"You are guiding the owner on their own Windows PC. Their goal: {_state['goal']}.\n"
        + (f"Reliable reference steps for this job: {recipe}\n" if recipe else "")
        + f"Steps you already told them:\n{done}\n\n"
        "Look at this screenshot of their screen right now. Tell them the ONE next thing to do: where it is on the "
        "screen (top-left, left menu, middle, bottom-right...), what it's labelled, and whether to click it or type. "
        "If the goal looks finished, say so. If what they need isn't on screen, tell them what to open first. "
        "Never ask them to share passwords or keys with you. If you're not sure what you're seeing, say so. "
        "Answer in 1 to 3 short sentences."
    )


def step(shoot=None, look=None):
    """One guide step. Returns (instruction, screenshot path or None)."""
    if not _state:
        return "No guide is running. Start one with /guide and what you want to do.", None
    shoot = shoot or echo_photos.screenshot
    look = look or (lambda image, question: echo_photos.look([image], question))
    if len(_state["steps"]) >= MAX_STEPS:
        return stop() + " (That was a lot of steps. Send /guide again to start fresh.)", None
    if not echo_photos.has_vision():
        _state.clear()
        return ("To guide you I need to see your screen, which needs the free photo brain on your PC "
                f"({echo_photos.VISION_MODEL}, {echo_photos.VISION_SIZE}). Send /getvision to download it, "
                "then send your /guide again."), None
    try:
        path = shoot()
        with open(path, "rb") as f:
            image = f.read()
        tip = (look(image, _prompt()) or "").strip() or "I couldn't make out the screen. Send 'next' to try again."
    except Exception as exc:
        return f"I couldn't look at your screen: {str(exc)[:200]}. Send 'next' to try again, or 'stop'.", None
    _state["steps"].append(tip[:300])
    _state["at"] = time.time()
    n = len(_state["steps"])
    return f"👉 Step {n}: {tip}\n\nDo that, then reply 'next'. Reply 'stop' to finish.", str(path)
