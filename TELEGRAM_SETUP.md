# Echo Telegram notifications

1. On Telegram, create a bot with the verified @BotFather account using `/newbot`.
2. Open your new bot's chat and press **Start**.
3. Get your numeric chat ID from @userinfobot.
4. On your Windows PC, open Notepad and save this JSON as `%USERPROFILE%\\.echo_telegram.json` (choose **All Files**, UTF-8):

```json
{"bot_token":"YOUR_BOTFATHER_TOKEN","chat_id":"YOUR_NUMERIC_CHAT_ID"}
```

**Never commit this file or share the token.** You can instead set `ECHO_TELEGRAM_TOKEN` and `ECHO_TELEGRAM_CHAT_ID` environment variables.

5. In the Echo folder run `py echo_telegram.py` to test. The bot should message your Telegram account.
6. Run `py echo_scheduler.py` to enable scheduled report notifications while the PC is on.
7. Run `py echo_preflight.py` any time to check setup. `telegram_notifications: configured` means reports will send.

Reports arrive at 6:30 AM, 1 PM and 5:30 PM Adelaide time. If the PC starts late, Echo sends only the latest missed report. A repeating error is sent at most once per hour.

Note: `echo_telegram_approved_updater.py` reads only the `ECHO_TELEGRAM_TOKEN` and `ECHO_TELEGRAM_CHAT_ID` environment variables, not the JSON file.

This module sends notifications only; it does not receive or authorize replies. Existing approval requirements still apply. Reports reflect the scheduler's actual tracked state, not assumed completed work.
