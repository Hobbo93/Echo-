# Echo-
My ai

## First-time setup (Windows)

1. Install [Python 3.11+](https://www.python.org/downloads/) (tick **Add python.exe to PATH**) and [Ollama](https://ollama.com).
2. Double-click **`setup_echo.bat`**. It installs everything, downloads the AI model, asks for your Telegram details (see `TELEGRAM_SETUP.md`; you can skip them and add them later) and checks everything is working.

## Running Echo

Double-click **`start_echo.bat`**. It opens each part of Echo in its own window and opens Echo HQ (the 3D office) in your browser at <http://127.0.0.1:5000>.

Parts that are not set up yet (for example Telegram) are skipped with a message saying how to turn them on. Close a window to stop that part.

| Part | What it does | Needs |
|---|---|---|
| Echo HQ (`echo_server.py`) | 3D office; chat with any of the 8 employees | Ollama |
| Scheduler (`echo_scheduler.py`) | Daily task queue, reports at 6:30 AM / 1 PM / 5:30 PM, lead research at 3 PM | Telegram for reports; Google Places key for leads |
| Updater (`echo_telegram_approved_updater.py`) | Asks on Telegram before installing any GitHub update | Telegram main bot |
| Telegram chat (`echo_telegram_chat.py`) | Chat with Echo from your phone (send `/new` to start fresh) | A second Telegram bot |

Other tools you can run by hand:

| What | Command |
|---|---|
| Check setup | `py echo_preflight.py` (any `error` line says what to fix) |
| Change settings | `py echo_setup.py` |
| Business lead research now | `py echo_leads.py` |
| Prepare a video clip | `py echo_content.py video.mp4 --start 0 --length 30` (needs FFmpeg) |

Echo never publishes, trades, spends money or contacts anyone without your approval.
