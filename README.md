# Echo-
My ai

## First-time setup (Windows)

1. Install Python 3.11+ and [Ollama](https://ollama.com), then run `ollama pull llama3.2`.
2. In the Echo folder run: `py -m pip install -r requirements.txt`
3. Set up Telegram: see `TELEGRAM_SETUP.md`.
4. Check everything: `py echo_preflight.py` (any `error` line says what to fix).

## Running Echo

| What | Command |
|---|---|
| Server for the 3D office | `py echo_server.py`, then open `Office.html` and press Test Connection |
| Daily tasks + Telegram reports | `py echo_scheduler.py` |
| Approval-gated updates | `py echo_telegram_approved_updater.py` |
| Telegram chat (separate bot) | `py echo_telegram_chat.py` |
| Business lead research | `py echo_leads.py` (needs `GOOGLE_PLACES_API_KEY`) |
| Prepare a video clip | `py echo_content.py video.mp4 --start 0 --length 30` (needs FFmpeg) |

Each runs in its own window. Echo never publishes, trades, spends money or contacts anyone without your approval.
