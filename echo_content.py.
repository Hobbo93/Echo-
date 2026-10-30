"""Echo Content Office: prepare and queue locally owned video clips.

Requires FFmpeg and ffprobe installed and available on PATH.
This module does not download third-party videos or publish anything.
"""
from pathlib import Path
from datetime import datetime, timezone
import json
import re
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "content_input"
OUTPUT = ROOT / "content_output"
QUEUE = ROOT / "content_queue.json"

def setup():
    for folder in (INPUT, OUTPUT):
        folder.mkdir(parents=True, exist_ok=True)
    if not QUEUE.exists():
        QUEUE.write_text("[]", encoding="utf-8")

def _run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])
    return result.stdout

def _duration(path):
    result = _run(["ffprobe", "-v", "error", "-show_entries",
                   "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)])
    return float(result.strip())

def _queue_read():
    return json.loads(QUEUE.read_text(encoding="utf-8"))

def prepare_clip(source, start=0, length=30, campaign="", caption=""):
    """Create a vertical MP4 from a local video and queue it for approval.

    start and length are seconds. This crops to 9:16; review framing manually.
    caption is stored as post text, not burned into the video.
    """
    setup()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Install FFmpeg and ensure ffmpeg and ffprobe are on PATH.")
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise ValueError("Provide a valid local video file (.mp4, .mov, .mkv, .webm).")
    start, length = float(start), float(length)
    if start < 0 or length <= 0 or length > 180:
        raise ValueError("Start must be >= 0 and clip length must be 1–180 seconds.")
    if start + length > _duration(source) + 0.05:
        raise ValueError("Requested clip extends beyond the video.")
    clip_id = uuid.uuid4().hex[:12]
    target = OUTPUT / f"{clip_id}.mp4"
    _run(["ffmpeg", "-y", "-ss", str(start), "-i", str(source),
          "-t", str(length), "-vf",
          "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
          "-r", "30", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
          "-b:a", "128k", "-movflags", "+faststart", str(target)])
    item = {"id": clip_id, "source": str(source), "video": str(target),
            "campaign": campaign, "caption": caption, "status": "pending_approval",
            "created_at": datetime.now(timezone.utc).isoformat()}
    queue = _queue_read()
    queue.append(item)
    QUEUE.write_text(json.dumps(queue, indent=2), encoding="utf-8")
    return item

def list_clips(status=None):
    setup()
    items = _queue_read()
    return [item for item in items if item["status"] == status] if status else items

def set_approval(clip_id, approved):
    """Local approval only; does not publish or submit the video."""
    setup()
    items = _queue_read()
    for item in items:
        if item["id"] == clip_id:
            if item["status"] != "pending_approval":
                raise ValueError("Clip has already been reviewed.")
            item["status"] = "approved" if approved else "rejected"
            QUEUE.write_text(json.dumps(items, indent=2), encoding="utf-8")
            return item
    raise KeyError("Clip not found.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Echo video clip preparation")
    parser.add_argument("source", nargs="?", help="Local video path")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--length", type=float, default=30)
    parser.add_argument("--campaign", default="")
    parser.add_argument("--caption", default="")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list_clips(), indent=2))
    elif args.source:
        print(json.dumps(prepare_clip(args.source, args.start, args.length,
                                      args.campaign, args.caption), indent=2))
    else:
        parser.print_help()
