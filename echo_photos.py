"""Photos for Echo: understand photos you send, and send photos back.

- Photos you send (Telegram or Echo HQ) are saved in %USERPROFILE%\\Echo_photos
  and Echo looks at them with a local vision model through Ollama (free).
- Echo can send you a screenshot of this PC, or any photo from Echo_photos.

The vision model is downloaded only when you ask (/getvision on Telegram, or
the button in Echo HQ). Standard library only.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OLLAMA_BASE = os.getenv("ECHO_OLLAMA_URL", "http://127.0.0.1:11434/api/chat").rsplit("/api/", 1)[0]
def vision_model():
    """The photo model (set by echo_brain; gemma3:4b unless upgraded)."""
    import echo_brain
    return echo_brain.vision_model()


VISION_SIZE = "about 3.3 GB"
PHOTO_DIR = Path.home() / "Echo_photos"
IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_IMAGE_BYTES = 15 * 1024 * 1024

SYSTEM_PROMPT = (
    "You are Echo, a practical personal AI assistant. The user has shared a photo. "
    "Describe what matters in it and answer their question clearly and briefly. "
    "If you can't make something out, say so instead of guessing. You cannot claim "
    "you performed actions outside this chat."
)

pull_state = {"running": False, "percent": 0, "status": "", "error": ""}


# ==========================================
# VISION MODEL
# ==========================================

def _get(path, timeout=10):
    with urllib.request.urlopen(OLLAMA_BASE + path, timeout=timeout) as r:
        return json.load(r)


def installed_models():
    try:
        return [m.get("name", "") for m in _get("/api/tags").get("models", [])]
    except (OSError, ValueError):
        return []


def has_vision():
    want = vision_model() if ":" in vision_model() else vision_model() + ":latest"
    return any(name == want or name == vision_model() for name in installed_models())


def pull_vision(progress=None):
    """Download the vision model. progress(percent, status) is called as it goes."""
    if pull_state["running"]:
        raise RuntimeError("The vision model is already downloading.")
    pull_state.update(running=True, percent=0, status="starting", error="")
    try:
        body = json.dumps({"model": vision_model(), "stream": True}).encode()
        req = urllib.request.Request(OLLAMA_BASE + "/api/pull", body,
                                     {"Content-Type": "application/json"})
        last = -1
        with urllib.request.urlopen(req, timeout=120) as r:
            for line in r:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise RuntimeError(data["error"])
                total, done = data.get("total"), data.get("completed")
                percent = int(done * 100 / total) if total and done else pull_state["percent"]
                pull_state.update(percent=percent, status=data.get("status", ""))
                if progress and percent // 25 != last // 25:
                    last = percent
                    progress(percent, data.get("status", ""))
        pull_state.update(percent=100, status="ready")
    except urllib.error.URLError:
        pull_state["error"] = "Cannot reach Ollama. Make sure the Ollama app is running."
        raise RuntimeError(pull_state["error"]) from None
    except Exception as exc:
        pull_state["error"] = str(exc)
        raise
    finally:
        pull_state["running"] = False


def pull_vision_in_background():
    if pull_state["running"]:
        return False
    threading.Thread(target=lambda: _quiet(pull_vision), daemon=True).start()
    return True


def _quiet(fn):
    try:
        fn()
    except Exception:
        pass


def need_vision_message(how="Send /getvision"):
    return ("To see photos I need a vision model (" + vision_model() + ", " + VISION_SIZE +
            ", free, runs on your PC). " + how + " to download it, then send the photo again.")


def look(images, question="", history=None):
    """Ask the vision model about one or more images (raw bytes)."""
    if not has_vision():
        raise RuntimeError(need_vision_message())
    question = question.strip() or "What's in this photo?"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *(history or []),
                {"role": "user", "content": question,
                 "images": [base64.b64encode(b).decode() for b in images]}]
    payload = {"model": vision_model(), "messages": messages, "stream": False}
    req = urllib.request.Request(OLLAMA_BASE + "/api/chat", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.load(r).get("message", {}).get("content", "").strip() or "I couldn't make out that photo."
    except urllib.error.URLError:
        raise RuntimeError("Cannot reach Ollama. Make sure the Ollama app is running.") from None


# ==========================================
# PHOTO FOLDER
# ==========================================

def image_type(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:2] == b"BM":
        return ".bmp"
    return None


def save_photo(data, prefix="photo"):
    ext = image_type(data)
    if not ext:
        raise RuntimeError("That file isn't a photo I can read (JPG, PNG, WEBP, GIF or BMP).")
    if len(data) > MAX_IMAGE_BYTES:
        raise RuntimeError("That photo is too large (15 MB max).")
    PHOTO_DIR.mkdir(exist_ok=True)
    path = PHOTO_DIR / (prefix + "_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ext)
    path.write_bytes(data)
    return path


def list_photos(limit=10):
    if not PHOTO_DIR.is_dir():
        return []
    files = [p for p in PHOTO_DIR.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_TYPES]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[:limit]


def find_photo(query):
    """'1' = newest photo, or part of a file name."""
    photos = list_photos(200)
    query = query.strip().lower()
    if query.isdigit() and 1 <= int(query) <= len(photos):
        return photos[int(query) - 1]
    for p in photos:
        if query and query in p.name.lower():
            return p
    return None


# ==========================================
# SCREENSHOT OF THIS PC
# ==========================================

_PS_SCREENSHOT = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save($args[0], [System.Drawing.Imaging.ImageFormat]::Png)
"""


def screenshot():
    """Save a screenshot of the whole screen into Echo_photos and return its path."""
    PHOTO_DIR.mkdir(exist_ok=True)
    path = PHOTO_DIR / ("screen_" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".png")
    try:
        from PIL import ImageGrab  # used if Pillow happens to be installed
        ImageGrab.grab(all_screens=True).save(path)
        return path
    except Exception:
        pass
    if sys.platform != "win32":
        raise RuntimeError("Screenshots are only set up for Windows.")
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as f:
        f.write(_PS_SCREENSHOT)
        script = f.name
    try:
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", script, str(path)], capture_output=True, timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    finally:
        os.unlink(script)
    if not path.exists():
        raise RuntimeError("Couldn't take a screenshot (is the PC locked or asleep?).")
    return path


# ==========================================
# MAKING PICTURES (free, no key: Pollinations)
# ==========================================

PICTURE_WORDS = re.compile(r"\b(?:send|show|make|draw|create|generate|give)\b.{0,20}?\b(?:me\s+)?(?:a|an|some)?\s*"
                           r"(?:picture|photo|pic|image|drawing|painting)s?\s+(?:of\s+)?(.+)", re.I)
VIDEO_WORDS = re.compile(r"\b(?:send|show|make|create|generate)\b.{0,20}?\bvideos?\b", re.I)


def picture_request(text):
    """'send me a picture of a red car' -> 'a red car', else None."""
    if text.lower().startswith(("/picture", "/draw", "/image")):
        return text.split(None, 1)[1] if len(text.split()) > 1 else None
    d = re.match(r"^\s*(?:can you |please |echo,? )?(?:draw|paint|sketch)\s+(?:me\s+)?(.+)", text, re.I)
    if d:
        return d.group(1).strip(" .!?")
    m = PICTURE_WORDS.search(text)
    if m and not SCREENSHOT_WORDS.search(text):
        return m.group(1).strip(" .!?")
    return None


def make_picture(prompt):
    """Create an image from a description; saved in Echo_photos. Returns the path."""
    import urllib.parse
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt[:400]) +
           "?width=1024&height=1024&nologo=true&seed=" + str(int(time.time()) % 100000))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Echo)"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read(MAX_IMAGE_BYTES)
    except Exception as exc:
        raise RuntimeError("The picture service didn't answer (" + type(exc).__name__ + "). Try again in a minute.") from None
    if not image_type(data):
        raise RuntimeError("The picture service sent something that isn't an image. Try again.")
    return save_photo(data, "made_for_you")


SCREENSHOT_WORDS = re.compile(r"\b(screenshot|screen ?shot|show me (my|the) (screen|pc|computer))\b", re.I)
