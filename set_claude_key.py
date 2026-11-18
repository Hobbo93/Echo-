"""Add your Anthropic API key on the PC (the private alternative to /connect 5 on Telegram).

Run: double-click "Set Claude Key.bat" (or: py set_claude_key.py)
The key is typed in hidden, saved only to %USERPROFILE%\\.echo_telegram.json (never the Echo folder),
tested, and then Echo switches to Claude within your monthly limit (default US$20).
"""
import getpass
import re
import sys

import echo_ai
import echo_connect


def main():
    print("ECHO - TURN ON CLAUDE")
    print("Copy your key from console.anthropic.com > API keys.")
    print("Right-click here to paste it (it stays hidden), then press Enter.\n")
    key = getpass.getpass("API key: ").strip()
    if not key:
        print("No key entered. Nothing changed.")
        return 1
    if not re.match(r"^sk-ant-\S{20,}$", key):
        print("That doesn't look like an Anthropic key (they start with sk-ant-). Nothing changed.")
        return 1
    echo_connect._save_setting("anthropic_api_key", key)
    print("\nKey saved. Testing it...")
    try:
        detail = echo_ai.test()
    except Exception as exc:
        print(f"\nThe key was saved but the test failed: {str(exc)[:250]}")
        print("If it mentions credit or billing, add credit at console.anthropic.com > Billing, then run this again.")
        return 1
    st = echo_ai.settings()
    st["provider"] = "claude"
    echo_ai.save_settings(st)
    print(f"\nSUCCESS: Echo now thinks with Claude. {detail}")
    print(f"Monthly limit: ${float(st['budget']):.2f}. At the limit Echo goes back to the free local brain until the 1st.")
    print("Check spending any time with /brain on Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
