"""Local speech for Echo: voice notes in, spoken replies out. No paid APIs.

Speech-to-text: faster-whisper (py -m pip install -r requirements-voice.txt),
or the original `whisper` command if that is installed instead.
Text-to-speech: Piper, a free natural-sounding voice (send /getvoice on Telegram once to
download it, about 85 MB), otherwise the voice built into Windows. Replies are sent as Telegram voice notes (OGG/Opus)
when they can be converted, otherwise as an audio file.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WHISPER_MODEL = os.getenv("ECHO_WHISPER_MODEL", "base")
PIPER_MODEL = os.getenv("ECHO_PIPER_MODEL", "").strip()
VOICE_DIR = Path.home() / "Echo_voice"
VOICE_CONFIG = Path.home() / ".echo_voice.json"
PIPER_ZIP = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
VOICES = {  # name: (voice file, what it sounds like)
    "american": ("en/en_US/lessac/medium/en_US-lessac-medium", "natural American voice"),
    "british": ("en/en_GB/alba/medium/en_GB-alba-medium", "natural British voice"),
}
VOICE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{path}{ext}"

_model = None


def can_transcribe():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return bool(shutil.which("whisper"))


def piper():
    """(piper program, voice file) if the natural voice is set up, else None."""
    try:
        cfg = json.loads(VOICE_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cfg = {}
    exe = cfg.get("piper") or shutil.which("piper")
    model = PIPER_MODEL or cfg.get("model", "")
    if exe and model and Path(exe).is_file() and Path(model).is_file():
        return exe, model
    return None


def can_speak():
    return bool(piper() or (sys.platform == "win32" and shutil.which("powershell")))


def _download(url, dest, progress=None):
    import urllib.request
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as out:
        total = int(r.headers.get("Content-Length") or 0)
        got, last = 0, -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress and total and got * 4 // total > last:
                last = got * 4 // total
                progress(f"Downloading {dest.name}: {got * 100 // total}%")
    tmp.replace(dest)


def setup_voice(which="american", progress=None, download=_download):
    """Download Piper and a voice from their official sources (free) and switch Echo to it.
    Returns a message. Windows only."""
    if sys.platform != "win32" and download is _download:
        return "The natural voice can only be set up on the Windows PC."
    import zipfile
    path, like = VOICES.get(which, VOICES["american"])
    VOICE_DIR.mkdir(parents=True, exist_ok=True)
    exe = VOICE_DIR / "piper" / "piper.exe"
    if not exe.is_file():
        zpath = VOICE_DIR / "piper_windows.zip"
        download(PIPER_ZIP, zpath, progress)
        with zipfile.ZipFile(zpath) as z:
            z.extractall(VOICE_DIR)
        zpath.unlink(missing_ok=True)
    model = VOICE_DIR / (path.rsplit("/", 1)[1] + ".onnx")
    for ext in (".onnx", ".onnx.json"):
        target = Path(str(model) + (".json" if ext == ".onnx.json" else ""))
        if not target.is_file():
            download(VOICE_URL.format(path=path, ext=ext), target, progress)
    if not exe.is_file():
        return "❌ The voice download didn't contain piper.exe. Nothing changed."
    VOICE_CONFIG.write_text(json.dumps({"piper": str(exe), "model": str(model), "voice": which}, indent=2),
                            encoding="utf-8")
    return (f"🗣️ Echo now speaks with a {like}. Send a voice note to hear it. "
            "To switch: /getvoice british or /getvoice american.")


def transcribe(path):
    """Turn an audio file (Telegram .ogg voice note) into text."""
    global _model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        WhisperModel = None
    if WhisperModel:
        if _model is None:
            print("Loading speech recognition (first time downloads ~150 MB)...", flush=True)
            _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _ = _model.transcribe(str(path), language="en", vad_filter=True)
        return " ".join(segment.text.strip() for segment in segments).strip()
    if shutil.which("whisper"):
        folder = Path(path).parent
        subprocess.run(["whisper", str(path), "--model", WHISPER_MODEL, "--language", "en",
                        "--output_dir", str(folder), "--output_format", "txt"],
                       check=True, timeout=300, capture_output=True)
        return (folder / (Path(path).stem + ".txt")).read_text(encoding="utf-8").strip()
    raise RuntimeError("Voice notes need speech recognition. Run setup_echo.bat and choose Y for voice.")


_WINDOWS_TTS = r"""
[Console]::InputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$au = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'en-AU' } | Select-Object -First 1
if ($au) { $s.SelectVoice($au.VoiceInfo.Name) }
$s.Rate = 1
$s.SetOutputToWaveFile($env:ECHO_WAV)
$s.Speak([Console]::In.ReadToEnd())
$s.Dispose()
"""


def synthesize(text, wav):
    """Write speech for text to a .wav file. Returns False if no voice is available."""
    natural = piper()
    if natural:
        subprocess.run([natural[0], "--model", natural[1], "--output_file", str(wav)],
                       input=text, text=True, encoding="utf-8", capture_output=True,
                       check=True, timeout=120)
        return True
    if sys.platform == "win32" and shutil.which("powershell"):
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WINDOWS_TTS],
                       input=text, text=True, encoding="utf-8", capture_output=True,
                       check=True, timeout=120, env={**os.environ, "ECHO_WAV": str(wav)})
        return Path(wav).is_file() and Path(wav).stat().st_size > 100
    return False


def to_voice_note(wav, ogg):
    """Convert .wav to OGG/Opus (Telegram voice note). Returns True on success."""
    if shutil.which("ffmpeg"):
        result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1",
                                 "-c:a", "libopus", "-b:a", "32k", str(ogg)],
                                capture_output=True, timeout=120)
        if result.returncode == 0:
            return True
    try:
        import av  # installed with faster-whisper
        with av.open(str(wav)) as source, av.open(str(ogg), "w", format="ogg") as target:
            stream = target.add_stream("libopus", rate=48000)
            stream.bit_rate = 32000
            resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
            for frame in source.decode(audio=0):
                for chunk in resampler.resample(frame):
                    for packet in stream.encode(chunk):
                        target.mux(packet)
            for packet in stream.encode(None):
                target.mux(packet)
        return Path(ogg).stat().st_size > 100
    except Exception:
        return False


def speak_to_file(text, folder):
    """Make a spoken reply in folder. Returns (path, is_voice_note) or (None, False)."""
    wav = Path(folder) / "reply.wav"
    if not synthesize(text, wav):
        return None, False
    ogg = Path(folder) / "reply.ogg"
    if to_voice_note(wav, ogg):
        return ogg, True
    return wav, False


if __name__ == "__main__":
    print("Speech recognition:", "ready" if can_transcribe() else "not installed")
    print("Spoken replies:", "ready" if can_speak() else "not available")
    if len(sys.argv) > 1:
        print("Heard:", transcribe(sys.argv[1]))
