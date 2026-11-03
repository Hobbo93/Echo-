"""Local speech for Echo: voice notes in, spoken replies out. No paid APIs.

Speech-to-text: faster-whisper (py -m pip install -r requirements-voice.txt),
or the original `whisper` command if that is installed instead.
Text-to-speech: Piper if ECHO_PIPER_MODEL points to a voice, otherwise the
voice built into Windows. Replies are sent as Telegram voice notes (OGG/Opus)
when they can be converted, otherwise as an audio file.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WHISPER_MODEL = os.getenv("ECHO_WHISPER_MODEL", "base")
PIPER_MODEL = os.getenv("ECHO_PIPER_MODEL", "").strip()

_model = None


def can_transcribe():
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return bool(shutil.which("whisper"))


def can_speak():
    return bool((shutil.which("piper") and PIPER_MODEL and Path(PIPER_MODEL).is_file())
                or (sys.platform == "win32" and shutil.which("powershell")))


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
    if shutil.which("piper") and PIPER_MODEL and Path(PIPER_MODEL).is_file():
        subprocess.run(["piper", "--model", PIPER_MODEL, "--output_file", str(wav)],
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
