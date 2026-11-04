# Echo-
My ai

## First-time setup (Windows)

1. Install [Python 3.11+](https://www.python.org/downloads/) (tick **Add python.exe to PATH**) and [Ollama](https://ollama.com).
2. Double-click **`setup_echo.bat`**. It installs everything, downloads the AI model, asks for your Telegram details (see `TELEGRAM_SETUP.md`; you can skip them and add them later) and checks everything is working.

## Talking to Echo

- **On your PC:** in Echo HQ, press **📞 Call Echo** and just talk. Echo listens, answers out loud and keeps the conversation going. Tap **✋ Interrupt** to cut in, say "bye" or tap **Hang up** to finish. Use Chrome or Edge, and allow the microphone. (Chrome turns your speech into text using Google's servers; Echo's answers still come from your PC.)
- **On Telegram:** send the Echo chat bot a voice note and it replies with a voice note. Choose **Y** for voice notes in `setup_echo.bat`.
- **Phone calls:** ring Echo, or have Echo ring you (**📱 Ring my phone** in Echo HQ, or `/callme` on Telegram). Needs a Twilio account: see `PHONE_SETUP.md`.

## Running Echo

Double-click **`start_echo.bat`**. It opens each part of Echo in its own window and opens Echo HQ (the 3D office) in your browser at <http://127.0.0.1:5000>.

Parts that are not set up yet (for example Telegram) are skipped with a message saying how to turn them on. Close a window to stop that part.

| Part | What it does | Needs |
|---|---|---|
| Echo HQ (`echo_server.py`) | 3D office; chat with any of the 8 employees | Ollama |
| Scheduler (`echo_scheduler.py`) | Daily task queue, reports at 6:30 AM / 1 PM / 5:30 PM, lead research at 3 PM | Telegram for reports; Google Places key for leads |
| Updater (`echo_telegram_approved_updater.py`) | Asks on Telegram before installing any GitHub update | Telegram main bot |
| Telegram chat (`echo_telegram_chat.py`) | Chat with Echo from your phone by text or voice note (`/new` starts fresh, `/callme` rings you) | A second Telegram bot |
| Phone line (`echo_phone.py`) | Ring Echo, or Echo rings you | Twilio + the free tunnel (`PHONE_SETUP.md`) |

Other tools you can run by hand:

| What | Command |
|---|---|
| Check setup | `py echo_preflight.py` (any `error` line says what to fix) |
| Change settings | `py echo_setup.py` |
| Business lead research now | `py echo_leads.py` |
| Prepare a video clip | `py echo_content.py video.mp4 --start 0 --length 30` (needs FFmpeg) |

Echo never publishes, trades, spends money or contacts anyone without your approval.

## Echo learns and tells the truth

- **Honest answers:** Echo is told to say "I don't know" instead of guessing, to point out problems, and never to claim it did something it didn't. It knows exactly which services are really connected. If a reply still claims something happened (like "I've posted it") or quotes "live" prices, Echo adds a ⚠️ honesty note.
- **Learns from you:** say "that's not true", "stop telling me what I want to hear", or `/feedback ...`. Echo saves it as a lesson. Every evening at 8:30 PM it reviews the day and updates how it talks to you, then sends you a short report. `/learned` shows what it has learned.
- **Researches while your PC is on:** every 90 minutes between 7 AM and 10 PM, Echo looks up one topic from real sources (Google News and Wikipedia, free) and saves notes with the sources. It researches what you ask first (`/research add dog bed prices` or "research cheap dog toys for me"), then questions it couldn't answer, then topics for your businesses. `/research` shows the list and the latest findings.
- **Smarter answers:** the default model (`llama3.2`) is small and makes things up more often. If your PC has 16 GB+ of memory, run `ollama pull qwen2.5:7b` and type `qwen2.5:7b` into an employee's **AI Model** box in Echo HQ.
