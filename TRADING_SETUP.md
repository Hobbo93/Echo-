# Echo Day Trading Desk

The **Day Trading Desk** does the research for you and only trades when you say so.

## What it does
- **Every weekday evening (7:30 PM Adelaide)** it scans 15 big US shares and ETFs (SPY, QQQ, Apple, Microsoft, Nvidia…) for the best setup: a pullback in an uptrend, not overbought.
- It texts your Echo bot a **chart picture** (blue = entry, red = stop-loss, green = target) and the plan: how many shares, stop-loss, target, and how much you'd risk (1% of the account, never more than 25% of it in one trade).
- Tap **✅ Place trade** and Echo places it with your broker as a bracket order (the stop-loss and take-profit are attached straight away), then sends you a **picture of the trade**. Tap **❌ Skip trade** and nothing happens. Ideas expire after an hour.
- Orders sent in the evening fill when the US market opens (about 1 AM Adelaide time).
- Ask any time: `/trade propose` (idea now), `/trade scan`, `/trade analyse NVDA`, `/trade positions`, `/trade stats`. Or chat with the Day Trading Desk in Echo HQ.

## Be realistic
No trader or bot wins every trade. This approach aims for wins about twice the size of losses, so it can be profitable while winning less than half the time, and it can still lose money. Check its record with `/trade stats` and on your paper account for a few weeks before using real money. This is education, not financial advice.

## Connect a broker (Alpaca)
Without a broker, approved ideas go into Echo's own paper journal.

1. Sign up at **alpaca.markets**. A paper (practice) account is free.
2. In the Alpaca dashboard, make sure **Paper Trading** is selected, then click **API Keys → Generate New Keys**. Copy the key ID and the secret.
3. Double-click `setup_echo.bat`, press Enter to keep your other settings, and paste the two Alpaca keys. Restart Echo with `start_echo`.

Echo now places approved trades in your **Alpaca paper account**, with practice money.

## Real money (only when you're ready)
Alpaca says it accepts customers from around the world. Check that Australia is accepted when you apply for a live account. Then generate **live** API keys, put them in with `setup_echo.bat`, and add `"alpaca_live": true` to the settings file `.echo_telegram.json` in your user folder. Echo will say **LIVE (real money)** on every trade it asks you about. To go back to practice, remove that line.

Echo never trades without your tap, and never withdraws or moves money.
