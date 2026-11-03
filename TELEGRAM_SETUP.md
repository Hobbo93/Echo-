# Echo Telegram setup

Echo uses two Telegram bots:

- **Main bot**: sends reports and alerts, and asks before installing updates.
- **Chat bot** (optional): lets you chat with Echo from your phone. It must be a different bot, because two programs can't read the same bot's messages.

## Steps

1. On Telegram, message the verified **@BotFather** and send `/newbot`. Copy the token it gives you. This is your main bot.
2. Send `/newbot` again to make a second bot for chatting, and copy that token too.
3. Open each new bot's chat and press **Start**.
4. Message **@userinfobot** to get your numeric chat ID.
5. Double-click `setup_echo.bat` (or run `py echo_setup.py`) and paste the values when asked. Echo sends a test message when it's done.

Settings are saved privately to `%USERPROFILE%\.echo_telegram.json`, outside the Echo folder, so they are never uploaded to GitHub. **Never share your bot tokens.**

The file looks like this, if you'd rather edit it in Notepad (save as UTF-8, **All Files**):

```json
{
  "bot_token": "MAIN_BOT_TOKEN",
  "chat_id": "YOUR_NUMERIC_CHAT_ID",
  "chat_bot_token": "SECOND_BOT_TOKEN",
  "google_places_key": "OPTIONAL_GOOGLE_PLACES_KEY"
}
```

Environment variables still work and take priority: `ECHO_TELEGRAM_TOKEN`, `ECHO_TELEGRAM_CHAT_ID`, `ECHO_CHAT_TELEGRAM_TOKEN`, `GOOGLE_PLACES_API_KEY`.

## What you'll get

- Reports at 6:30 AM, 1 PM and 5:30 PM Adelaide time while the PC is on. If the PC starts late, only the latest missed report is sent.
- The top 5 business leads at 3 PM, if a Google Places key is set.
- A repeating error is sent at most once per hour.
- Update requests: reply `APPROVE <code>` or `REJECT <code>` to the main bot.

Run `py echo_preflight.py` any time to check the setup.
