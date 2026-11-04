"""Echo's brain: which free AI model (via Ollama) every part of Echo uses, and upgrading it.

    /brain           checks this PC (memory and graphics card) and recommends the best free model
    /brain upgrade   downloads it (free, can take a while), tests it, and switches Echo over
    /brain small     goes back to the small, fast model

Every part of Echo asks this module which model to use, so one switch changes them all.
Phone calls keep a fast model unless the PC has a good graphics card, because a slow answer
would make Twilio hang up (it waits about 15 seconds). Settings: %USERPROFILE%\\.echo_brain.json.
An ECHO_MODEL / ECHO_VISION_MODEL environment variable still overrides everything.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

SETTINGS = Path.home() / ".echo_brain.json"
OLLAMA_BASE = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat").rsplit("/api/", 1)[0]

SMALL, VISION_SMALL = "llama3.2", "gemma3:4b"
TIERS = {  # name: (main model, vision model, download size, what it's like)
    "small": (SMALL, VISION_SMALL, "already installed", "fast but basic; makes things up more often"),
    "medium": ("qwen2.5:7b", VISION_SMALL, "about 4.7 GB", "noticeably smarter and more honest"),
    "large": ("gemma3:12b", "gemma3:12b", "about 8.1 GB", "much smarter, and reads screenshots far better"),
}


# ==========================================
# WHICH MODEL TO USE (everything in Echo calls these)
# ==========================================

def _settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(s):
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def model():
    """Main model for chat, employees, research and summaries."""
    return os.getenv("ECHO_MODEL") or _settings().get("model") or SMALL


def fast_model():
    """For phone calls, where an answer must come within seconds."""
    return os.getenv("ECHO_MODEL") or _settings().get("fast_model") or SMALL


def vision_model():
    return os.getenv("ECHO_VISION_MODEL") or _settings().get("vision_model") or VISION_SMALL


KEEP_ALIVE = "30m"  # keep the model loaded this long after a chat, so replies stay quick
ACTIVITY = Path.home() / ".echo_activity"


def mark_active():
    """Call when the owner talks to Echo (chat, office, phone). Background jobs wait for a quiet spell."""
    try:
        ACTIVITY.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        pass


def owner_active(minutes=4):
    """True if the owner talked to Echo in the last few minutes (any part of Echo)."""
    try:
        return time.time() - float(ACTIVITY.read_text(encoding="utf-8")) < minutes * 60
    except (OSError, ValueError):
        return False


def resolve(name):
    """An employee's model setting: the old default (or blank) means 'Echo's brain'."""
    name = (name or "").strip()
    return model() if name in ("", "default", SMALL) else name


# ==========================================
# WHAT THIS PC CAN RUN
# ==========================================

_PS_SPECS = r"""
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$gpus = @()
Get-ItemProperty 'HKLM:\SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*' -ErrorAction SilentlyContinue |
  ForEach-Object { if ($_.DriverDesc) { $gpus += @{ name = $_.DriverDesc; vram = [int64]$_.'HardwareInformation.qwMemorySize' } } }
@{ ram = $ram; gpus = $gpus } | ConvertTo-Json -Depth 4 -Compress
"""


def specs():
    """{'ram_gb': float, 'gpu': name or '', 'vram_gb': float} for this PC (Windows)."""
    if sys.platform != "win32":
        raise RuntimeError("I can only check the PC's hardware on Windows.")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SPECS],
                       capture_output=True, text=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(r.stdout or "{}")
    gpus = data.get("gpus") or []
    gpus = [gpus] if isinstance(gpus, dict) else gpus
    return pick_gpu(float(data.get("ram") or 0) / 2**30, gpus)


def pick_gpu(ram_gb, gpus):
    """Keep the best graphics card Ollama can actually use (NVIDIA, or AMD Radeon RX)."""
    best = {"ram_gb": round(ram_gb, 1), "gpu": "", "vram_gb": 0.0}
    for g in gpus:
        name = str(g.get("name", ""))
        vram = float(g.get("vram") or 0) / 2**30
        usable = re.search(r"nvidia|geforce|rtx|gtx|quadro|radeon\s+(rx|pro)", name, re.I)
        if usable and vram > best["vram_gb"]:
            best.update(gpu=name, vram_gb=round(vram, 1))
    return best


def recommend(s):
    """(tier, reason, fast enough for phone calls?) for these specs."""
    vram, ram = s["vram_gb"], s["ram_gb"]
    if vram >= 11.5:
        return "large", f"your {s['gpu']} has {vram:g} GB of video memory", True
    if vram >= 6:
        return "medium", f"your {s['gpu']} has {vram:g} GB of video memory", True
    if ram >= 15:
        return "medium", (f"you have {ram:g} GB of memory but no graphics card Echo can use, so replies will be "
                          "slower (often 20 to 60 seconds); phone calls stay on the fast model"), False
    return "small", f"you have {ram:g} GB of memory and no usable graphics card, so a bigger model would be too slow", False


def describe():
    try:
        s = specs()
    except Exception as exc:
        return f"I couldn't check the PC's hardware ({str(exc)[:150]}). Echo is using {model()}."
    tier, why, phone_ok = recommend(s)
    main, vision, size, like = TIERS[tier]
    lines = [f"🧠 Echo's brain right now: {model()} (phone calls: {fast_model()}, photos: {vision_model()})",
             f"This PC: {s['ram_gb']:g} GB memory, graphics: {s['gpu'] or 'none Echo can use'}"
             + (f" ({s['vram_gb']:g} GB)" if s['vram_gb'] else "")]
    if main == model():
        lines.append(f"\nYou're already on the best model for this PC ({main}).")
    elif tier == "small":
        lines.append(f"\nBest for this PC: stay on {SMALL}, because {why}.")
    else:
        lines.append(f"\nBest for this PC: {main} ({like}), because {why}.\n"
                     f"Download: {size}, free. Send /brain upgrade to switch (you can go back with /brain small).")
    return "\n".join(lines)


# ==========================================
# UPGRADING (download, test, switch)
# ==========================================

state = {"running": False}


def installed():
    try:
        with urllib.request.urlopen(OLLAMA_BASE + "/api/tags", timeout=10) as r:
            return [m.get("name", "") for m in json.load(r).get("models", [])]
    except (OSError, ValueError):
        return []


def _has(name):
    want = name if ":" in name else name + ":latest"
    return any(n in (name, want) for n in installed())


def pull(name, progress=None):
    """Download a model through Ollama. progress(text) is called at each 25%."""
    if _has(name):
        return
    body = json.dumps({"model": name, "stream": True}).encode()
    req = urllib.request.Request(OLLAMA_BASE + "/api/pull", body, {"Content-Type": "application/json"})
    last = -1
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            for line in r:
                if not line.strip():
                    continue
                d = json.loads(line)
                if d.get("error"):
                    raise RuntimeError(d["error"])
                total, done = d.get("total"), d.get("completed")
                pct = int(done * 100 / total) if total and done else 0
                if progress and pct // 25 > last // 25:
                    last = pct
                    progress(f"Downloading {name}: {pct}%")
    except urllib.error.URLError:
        raise RuntimeError("Cannot reach Ollama. Make sure the Ollama app is running.") from None


def speed_test(name):
    """Seconds for a short answer (the first one includes loading the model)."""
    payload = {"model": name, "stream": False, "options": {"num_predict": 40},
               "messages": [{"role": "user", "content": "In one short sentence, say you're ready to help."}]}
    req = urllib.request.Request(OLLAMA_BASE + "/api/chat", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    for attempt in range(2):  # the second run shows the real speed once the model is loaded
        start = time.time()
        with urllib.request.urlopen(req, timeout=600) as r:
            json.load(r)
        took = time.time() - start
    return took


def upgrade(notify, tier=None, s=None):
    """Download the recommended model, test it and switch Echo to it. Reports through notify(text)."""
    if state["running"]:
        notify("The brain upgrade is already running.")
        return
    state["running"] = True
    try:
        s = s or specs()
        rec, why, phone_ok = recommend(s)
        tier = tier or rec
        main, vision, size, _like = TIERS[tier]
        if tier == "small":
            notify(f"This PC is best on the small model, because {why}. Staying on {SMALL}.")
            return
        notify(f"⬇️ Upgrading Echo's brain to {main} ({size}, free). This can take a while; "
               "Echo keeps working on the old brain meanwhile.")
        for name in dict.fromkeys([main, vision]):
            pull(name, notify)
        took = speed_test(main)
        settings = _settings()
        settings.update(model=main, vision_model=vision, fast_model=main if phone_ok else SMALL, tier=tier)
        _save(settings)
        msg = f"✅ Echo now thinks with {main}. A short answer took {took:.0f} seconds."
        if not phone_ok:
            msg += f" Phone calls stay on {SMALL} so they're quick enough."
        if took > 45:
            msg += " That's slow: if it bothers you, send /brain small to switch back."
        notify(msg)
    except Exception as exc:
        notify(f"❌ The brain upgrade didn't finish: {str(exc)[:200]}. Echo is still on {model()}.")
    finally:
        state["running"] = False


def downgrade():
    s = _settings()
    s.update(model=SMALL, vision_model=VISION_SMALL, fast_model=SMALL, tier="small")
    _save(s)
    return f"🧠 Back on the small, fast brain ({SMALL}). The bigger model stays downloaded if you want it again."


def handle(text, notify):
    """Telegram /brain commands. Returns a reply now (upgrades report through notify)."""
    t = text.strip().lower()
    if re.match(r"^/brain\s+(upgrade|bigger|smarter)", t):
        threading.Thread(target=upgrade, args=(notify,), daemon=True).start()
        return "🧠 Checking the PC and starting the upgrade…"
    if re.match(r"^/brain\s+(small|reset|fast|back)", t):
        return downgrade()
    return describe()
