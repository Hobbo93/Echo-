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

**Chart screenshots:** send Echo a screenshot of a chart on Telegram with "what do I do?" or the ticker (e.g. "NVDA") as the caption. The Trading Analyst reads it, runs Echo's analysis on live prices, and sends back the plan plus a chart with the entry (blue), stop-loss (red) and target (green). It never places a trade from a screenshot.

**Trading stop button:** say "stop trading" (or `/stoptrading`) and Echo pauses all trading at once: no new trade ideas, no new buys, and any waiting idea is cancelled. Open trades keep their stop-loss and target. "sell everything" sells every open position (asks Yes first). "resume trading" turns it back on.

## Echo on your PC (from Telegram)

Say "search youtube for dog grooming tips", "google cheap dog beds", "open my shopify admin" or "open gmail", and Echo opens it on the PC and sends you a screenshot. `/screen` (or "show me my screen") sends a picture of the screen any time. Echo only opens web pages; it never clicks, types or enters passwords.

**Guide mode:** `/guide connect my shopify store` (or "walk me through ...", "show me how to ..."). Echo looks at your screen, sends the screenshot with the next step ("click the green Create app button, top right"), and you do the clicking. Reply `next` after each step, `stop` to finish. Needs the free photo brain (`/getvision`).

## Short videos with OpusClip

**Find videos:** say "find videos about funny dog fails" (or "find long videos about …" for ones over 5 minutes) and Echo sends the top 5 from YouTube with links, free with no key. "clip 2" sends one to OpusClip; "open 2" plays it on the PC. For TikTok, Instagram or Facebook, tap Share → Copy link in the app, paste it to Echo, then say "clip it". Only clip videos you own or have permission to use.

**Brand Studio:** `/brand` for your clothing brand: design ideas, free mock-up pictures, shop listings, a launch plan, and drafts in Shopify after your Yes. See `BRAND_SETUP.md`.


Send `/clip` and a video link (or `/clip latest` for the newest video in `content_input`), and OpusClip cuts it into short clips. Echo messages you when they're ready. `/post 1 youtube instagram` (add `at 6pm` to schedule) posts a clip after you tap Yes. Setup: `OPUSCLIP_SETUP.md`.

## Selling websites (free)

- **Leads:** every day at 3 PM (or `/findleads`) Echo finds 20 local southern Adelaide businesses that need a website. With no Google key it uses OpenStreetMap, which is completely free with no card. A Google key adds more phone numbers and photos, and stays inside Google's free allowance.
- **Sell:** say `sell Pizza at Christies`. Echo writes a text, an email and a phone opener, and builds a **free preview website of their business** that it sends to your phone, ready to show the owner. `preview <name>` makes just the site.
- **Price:** `my website price is $499` puts your price in every pitch.
- **Follow up:** every morning at 9, Echo lists who's due a follow-up. `mark <name> won` when they say yes. `/sales` (and every Monday) shows the scoreboard.
- Echo never contacts businesses itself: you send the messages.

## Looking after itself (free)

- **Plan:** set goals ("my goal is $3,000 a month from websites"). The CEO turns them into a weekly plan with a job for each employee, sends today's top 3 each morning at 8:30, and research tasks go straight to the Research Agent. `/plan`, `/plan new`, `/done 2`.
- **Problems:** anything that goes wrong is written to `Echo_logs\errors.log`. From 8 AM, if something broke, Echo texts you a short list. `/errors` shows the last 3 days.
- **Health check:** every Sunday at 10 AM (or `/health`), Echo checks its parts, AI, connections, problems, backups and disk space, with a fix for anything wrong.
- **Backups:** every night Echo zips its memory, records and settings (never your keys or passwords) into `Echo_backups` in OneDrive, Dropbox or Google Drive if you have one, otherwise Documents. The last 14 are kept. `/backup` backs up now.
- **Natural voice:** `/getvoice` downloads Piper, a free natural voice, for Echo's voice notes (`/getvoice british` for a British one).
- **No jams:** research and summaries wait while you're talking to Echo, so chats and phone calls always get the AI first.

## A smarter brain (free)

Send `/brain` on Telegram. Echo checks your PC's memory and graphics card and recommends the best free AI model it can run. `/brain upgrade` downloads it (it can take a while), tests it and switches every part of Echo over. `/brain small` goes back to the small, fast model. Phone calls keep a fast model unless your PC has a good graphics card.

## Echo learns and tells the truth

- **Honest answers:** Echo is told to say "I don't know" instead of guessing, to point out problems, and never to claim it did something it didn't. It knows exactly which services are really connected. If a reply still claims something happened (like "I've posted it") or quotes "live" prices, Echo adds a ⚠️ honesty note.
- **Learns from you:** say "that's not true", "stop telling me what I want to hear", or `/feedback ...`. Echo saves it as a lesson. Every evening at 8:30 PM it reviews the day and updates how it talks to you, then sends you a short report. `/learned` shows what it has learned.
- **Researches while your PC is on:** every 90 minutes between 7 AM and 10 PM, Echo looks up one topic from real sources (Google News and Wikipedia, free) and saves notes with the sources. It researches what you ask first (`/research add dog bed prices` or "research cheap dog toys for me"), then questions it couldn't answer, then topics for your businesses. `/research` shows the list and the latest findings.
- **Smarter answers:** the default model (`llama3.2`) is small and makes things up more often. Send `/brain` to get a bigger free model if your PC can run it.
