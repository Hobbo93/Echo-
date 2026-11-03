# Echo Day Trading Desk

The **Day Trading Desk** does the research for you and only trades when you say so.

## What it does
- **Every weekday evening (7:30 PM Adelaide)** it scans 15 big US shares and ETFs (SPY, QQQ, Apple, Microsoft, Nvidia…) for the best setup: a pullback in an uptrend, not overbought.
- It texts your Echo bot a **chart picture** (blue = entry, red = stop-loss, green = target) and the plan: how many shares, stop-loss, target, and how much you'd risk (1% of the account, never more than 25% of it in one trade).
- Tap **✅ Place trade** and Echo places it with your broker as a bracket order (the stop-loss and take-profit are attached straight away), then sends you a **picture of the trade**. Tap **❌ Skip trade** and nothing happens. Ideas expire after an hour.
- Orders sent in the evening fill when the US market opens (about 1 AM Adelaide time).
- Ask any time: `/trade propose` (idea now), `/trade scan`, `/trade analyse NVDA`, `/trade positions`, `/trade stats`. Or chat with the Day Trading Desk in Echo HQ.

## Put your own money into a trade
Tell the Day Trading Desk (Echo HQ or Telegram) how much and which stock:
- **`put $500 into NVDA`** (also: `buy $300 of AAPL`, `invest $1000 in SPY`)

Echo works out how many shares that buys, sets a stop-loss (1.5× the daily range below) and a take-profit target (twice as far above), and sends you the chart with **✅ Place trade / ❌ Skip trade**. If the chart is pointing down, it warns you first.

After your one tap it **buys, then sells for you automatically**: at the target to take the profit, or at the stop-loss to cut the loss. You don't have to watch it.
- With Alpaca connected, the stop and target sit at the broker as a bracket order, so they work even if your PC is off.
- Without Alpaca, it runs in Echo's practice account and Echo checks the price every 5 minutes and sells at the stop or target, then texts you.
- **`sell NVDA`** sells the whole position now (after a Yes).
- `/trade positions` shows what you hold.

Amounts buy whole shares (US shares only through Alpaca). Prices are in US dollars.

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

## Trench mode (the default)
Trench (trench.io) has no API, so Echo doesn't click trades there. Instead:
- `/market` shows **🟢 UP / 🔴 DOWN / ⚪ WAIT** for every stock on the watchlist, plus a chart of the S&P 500.
- The evening scan (or `/trade propose`) sends the best UP **or** DOWN idea with a chart. Tap **✅ Place trade** and you get a **Trench ticket**: direction, stake, a safe multiplier, entry, and where to close.
- You place it on Trench yourself. Echo **watches the price every 5 minutes** and texts you **🔴 CLOSE NOW** at the stop-loss or **🟢 TAKE PROFIT** at the target.
- `/trade bankroll 500` sets your Trench bankroll; each ticket stakes 2% of it. `/trade open trades` lists what Echo is watching. `/trade stats` shows how many ideas hit their target.
- `/trade venue alpaca` switches to placing orders with your Alpaca broker instead (`/trade venue trench` switches back).

Trench's multiplier can lose your whole stake quickly, and its licensing isn't publicly confirmed. Only stake money you can afford to lose.
