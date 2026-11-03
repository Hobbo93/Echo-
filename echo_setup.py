"""Guided Echo setup. Run: py echo_setup.py

Asks for your Telegram bot tokens and chat ID (and an optional Google Places
key), saves them privately to %USERPROFILE%\\.echo_telegram.json, and sends a
test message. Press Enter to keep any value that is already saved.
"""
import json
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"

FIELDS = [
    ("bot_token", "Main bot token (reports + update approvals), from @BotFather"),
    ("chat_id", "Your numeric chat ID, from @userinfobot"),
    ("chat_bot_token", "Second bot token for chatting with Echo (optional)"),
    ("google_places_key", "Google Places API key for lead research (optional)"),
]

PHONE_FIELDS = [
    ("twilio_account_sid", "Twilio Account SID (starts with AC)"),
    ("twilio_auth_token", "Twilio Auth Token"),
    ("twilio_number", "Your Twilio phone number, e.g. +61412345678"),
    ("my_phone", "YOUR mobile number, e.g. +61412345678"),
]


def mask(value):
    return value[:4] + "…" + value[-3:] if len(value) > 10 else value


def main():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}

    print("ECHO SETUP")
    print("Settings are saved to", CONFIG)
    print("Press Enter to keep the current value.\n")

    def ask(fields):
        for key, label in fields:
            current = str(data.get(key, "")).strip()
            shown = f" [{mask(current)}]" if current else ""
            answer = input(f"{label}{shown}: ").strip()
            if answer:
                data[key] = answer.replace(" ", "") if key in ("twilio_number", "my_phone") else answer

    ask(FIELDS)

    phone = input("\nSet up phone calls so Echo can ring you? Needs a Twilio account "
                  "(see PHONE_SETUP.md) (y/N): ").strip().lower()
    if phone.startswith("y"):
        ask(PHONE_FIELDS)
        for key in ("twilio_number", "my_phone"):
            value = str(data.get(key, ""))
            if value and not (value.startswith("+") and value[1:].isdigit()):
                print(f"\n{key} must look like +61412345678 (with +61, no leading 0). Please run setup again.")
                return

    chat_id = str(data.get("chat_id", ""))
    if chat_id and not chat_id.lstrip("-").isdigit():
        print("\nChat ID must be a number (from @userinfobot). Please run setup again.")
        return
    if data.get("chat_bot_token") and data.get("chat_bot_token") == data.get("bot_token"):
        print("\nThe chat bot needs its own token, different from the main bot. Please run setup again.")
        return

    CONFIG.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("\nSaved.")

    if data.get("bot_token") and chat_id:
        from echo_telegram import send_message
        if send_message("Echo is set up and connected."):
            print("Test message sent - check Telegram.")
        else:
            print("Could not send a test message. Check the bot token, and press Start in your bot's chat.")


if __name__ == "__main__":
    main()
