"""Echo Day Trading Desk: research, risk plans, paper journal, and trades you approve.

Echo never moves money, and only places a trade after you tap Place trade. It reads public price data,
explains what the chart shows, suggests a risk plan (stop-loss and position
size), and lets you paper trade so its real, honest win rate is measured
before you risk anything. No strategy wins every trade; risk control is what
keeps an account alive.

Commands (Echo HQ chat with the Day Trading Desk, or /trade on Telegram):
  analyse BHP.AX        chart read + risk plan (ASX codes end in .AX; BTC-USD, AAPL…)
  paper buy BHP.AX 100  open a paper position at the live price
  paper sell BHP.AX     close it (or part: paper sell BHP.AX 50)
  positions             open paper positions with live profit/loss
  stats                 win rate, profit/loss, best/worst trade
  scan                  best setups on the watchlist right now
  /trade propose        top idea with a chart; tap Place trade (your approval) to place it
Data: Yahoo Finance public charts (may be delayed). Not financial advice.
"""
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DIR = Path.home() / "Echo_trading"
JOURNAL = DIR / "journal.json"
START_BALANCE = 10_000.0
RISK_PER_TRADE = 0.01  # risk 1% of the paper account per trade

DISCLAIMER = ("Education, not financial advice. No strategy wins every trade. "
              "Echo only places a trade after you approve it.")


# ==========================================
# PRICES
# ==========================================

def candles(symbol, rng="6mo", interval="1d"):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol.upper())
           + "?range=" + rng + "&interval=" + interval)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Echo trading desk)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.load(r)
    except Exception as exc:
        raise RuntimeError("Couldn't get prices for " + symbol.upper() + " (" + type(exc).__name__ +
                           "). Check the code: ASX shares end in .AX, e.g. BHP.AX.") from None
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        raise RuntimeError("No price data for " + symbol.upper() + ". ASX codes end in .AX, e.g. CBA.AX.")
    res = result[0]
    q = res["indicators"]["quote"][0]
    rows = [(t, o, h, l, c, v) for t, o, h, l, c, v in
            zip(res.get("timestamp", []), q["open"], q["high"], q["low"], q["close"], q["volume"])
            if None not in (o, h, l, c)]
    if len(rows) < 30:
        raise RuntimeError("Not enough price history for " + symbol.upper() + ".")
    meta = res.get("meta", {})
    return rows, meta


def live_price(symbol):
    rows, meta = candles(symbol, "5d", "1d")
    return float(meta.get("regularMarketPrice") or rows[-1][4]), meta.get("currency", "")


# ==========================================
# ANALYSIS
# ==========================================

def sma(values, n):
    return sum(values[-n:]) / n


def rsi(closes, n=14):
    gains = losses = 0.0
    for a, b in zip(closes[-n - 1:-1], closes[-n:]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return 100 - 100 / (1 + rs)


def atr(rows, n=14):
    trs = []
    for prev, cur in zip(rows[-n - 1:-1], rows[-n:]):
        trs.append(max(cur[2] - cur[3], abs(cur[2] - prev[4]), abs(cur[3] - prev[4])))
    return sum(trs) / n


def analyse(symbol):
    rows, meta = candles(symbol)
    closes = [r[4] for r in rows]
    price = float(meta.get("regularMarketPrice") or closes[-1])
    cur = meta.get("currency", "")
    s20, s50 = sma(closes, 20), sma(closes, min(50, len(closes)))
    r = rsi(closes)
    a = atr(rows)
    hi20, lo20 = max(x[2] for x in rows[-20:]), min(x[3] for x in rows[-20:])
    change_5d = (closes[-1] / closes[-6] - 1) * 100

    trend = ("uptrend" if price > s20 > s50 else "downtrend" if price < s20 < s50 else "sideways / mixed")
    if r >= 70:
        momentum = "overbought (RSI " + format(r, ".0f") + "): pullbacks are common from here"
    elif r <= 30:
        momentum = "oversold (RSI " + format(r, ".0f") + "): bounces happen, but falling knives too"
    else:
        momentum = "neutral (RSI " + format(r, ".0f") + ")"

    if trend == "uptrend" and r < 70:
        idea = "Bias: long setups only. Wait for a dip towards the 20-day average rather than chasing."
    elif trend == "downtrend":
        idea = "Bias: stand aside (or short, if you trade that way). Buying a downtrend is lower odds."
    else:
        idea = "Bias: no clear edge. Range trade between support and resistance, or wait."

    stop = price - 1.5 * a
    target = price + 3 * a
    acct = account_value()
    risk_dollars = acct * RISK_PER_TRADE
    qty = max(1, math.floor(risk_dollars / max(price - stop, 1e-9)))
    f = lambda v: format(v, ",.2f")
    return "\n".join([
        f"{symbol.upper()} {f(price)} {cur} ({change_5d:+.1f}% over 5 days)",
        f"Trend: {trend} (20-day avg {f(s20)}, 50-day avg {f(s50)})",
        f"Momentum: {momentum}",
        f"Daily range (ATR): {f(a)} · 20-day support {f(lo20)} · resistance {f(hi20)}",
        "",
        idea,
        f"Risk plan if you go long now: stop {f(stop)} (1.5× ATR), target {f(target)} (2:1 reward/risk).",
        f"Size: {qty} shares risks about ${f(risk_dollars)} (1% of the ${f(acct)} paper account).",
        "",
        f"Test it first: paper buy {symbol.upper()} {qty}",
        DISCLAIMER,
    ])


# ==========================================
# PAPER JOURNAL
# ==========================================

def _load():
    try:
        return json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"cash": START_BALANCE, "positions": {}, "closed": []}


def _save(j):
    DIR.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(j, indent=2), encoding="utf-8")


def account_value():
    j = _load()
    return j["cash"] + sum(p["qty"] * p["entry"] for p in j["positions"].values())


def paper_buy(symbol, qty):
    symbol = symbol.upper()
    price, cur = live_price(symbol)
    j = _load()
    cost = price * qty
    if cost > j["cash"]:
        return f"Not enough paper cash: {qty} × {price:,.2f} = {cost:,.2f}, cash is {j['cash']:,.2f}."
    p = j["positions"].get(symbol, {"qty": 0, "entry": 0.0, "opened": datetime.now(timezone.utc).isoformat()})
    p["entry"] = (p["entry"] * p["qty"] + cost) / (p["qty"] + qty)
    p["qty"] += qty
    j["positions"][symbol] = p
    j["cash"] -= cost
    _save(j)
    return f"Paper bought {qty} {symbol} at {price:,.2f} {cur}. Cash left {j['cash']:,.2f}. (Not a real trade.)"


def paper_sell(symbol, qty=None):
    symbol = symbol.upper()
    j = _load()
    p = j["positions"].get(symbol)
    if not p:
        return f"No paper position in {symbol}."
    qty = min(qty or p["qty"], p["qty"])
    price, cur = live_price(symbol)
    pnl = (price - p["entry"]) * qty
    j["cash"] += price * qty
    j["closed"].append({"symbol": symbol, "qty": qty, "entry": p["entry"], "exit": price, "pnl": pnl,
                        "closed": datetime.now(timezone.utc).isoformat()})
    p["qty"] -= qty
    if p["qty"] <= 0:
        del j["positions"][symbol]
    _save(j)
    return (f"Paper sold {qty} {symbol} at {price:,.2f} {cur}: {'profit' if pnl >= 0 else 'loss'} "
            f"{pnl:+,.2f}. Cash {j['cash']:,.2f}.")


def positions():
    j = _load()
    if not j["positions"]:
        return f"No open paper positions. Paper cash: {j['cash']:,.2f}."
    lines = ["Open paper positions:"]
    for sym, p in j["positions"].items():
        try:
            price, _ = live_price(sym)
            lines.append(f"{sym}: {p['qty']} @ {p['entry']:,.2f} → {price:,.2f} ({(price - p['entry']) * p['qty']:+,.2f})")
        except RuntimeError:
            lines.append(f"{sym}: {p['qty']} @ {p['entry']:,.2f} (price unavailable)")
    lines.append(f"Cash: {j['cash']:,.2f}")
    return "\n".join(lines)


def stats():
    j = _load()
    c = j["closed"]
    if not c:
        return "No closed paper trades yet. Try: analyse BHP.AX, then paper buy."
    wins = [t for t in c if t["pnl"] > 0]
    total = sum(t["pnl"] for t in c)
    best = max(c, key=lambda t: t["pnl"])
    worst = min(c, key=lambda t: t["pnl"])
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    losses = [t for t in c if t["pnl"] <= 0]
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    return "\n".join([
        f"Paper trades closed: {len(c)} · Win rate: {len(wins) / len(c) * 100:.0f}%",
        f"Total P/L: {total:+,.2f} · Account: {account_value():,.2f} (started {START_BALANCE:,.0f})",
        f"Average win {avg_win:+,.2f} · average loss {avg_loss:+,.2f}",
        f"Best: {best['symbol']} {best['pnl']:+,.2f} · Worst: {worst['symbol']} {worst['pnl']:+,.2f}",
        "Honest numbers: a good trader can win under half the time and still profit if wins are bigger than losses.",
    ])


# ==========================================
# COMMANDS
# ==========================================

SYMBOL = r"([A-Za-z0-9.\-^=]{1,15})"


def handle(text):
    """Run a trading command. Returns a reply, or None if it isn't one."""
    t = text.strip()
    low = t.lower()
    try:
        m = re.match(r"^(?:/trade\s+)?paper\s+buy\s+" + SYMBOL + r"\s+(\d+)", t, re.I)
        if m:
            return paper_buy(m.group(1), int(m.group(2)))
        m = re.match(r"^(?:/trade\s+)?paper\s+sell\s+" + SYMBOL + r"(?:\s+(\d+))?", t, re.I)
        if m:
            return paper_sell(m.group(1), int(m.group(2)) if m.group(2) else None)
        if re.search(r"\b(positions|portfolio|holdings)\b", low):
            return positions()
        if re.search(r"\b(stats|win rate|performance|journal)\b", low):
            return stats()
        if re.search(r"\b(scan|find (a )?trade|best trade|any trades?)\b", low):
            best = scan(top=3)
            if not best:
                return "No good setups on the watchlist right now. Sitting out is a valid trade."
            return "Best setups now (send /trade propose to get the top one with a chart and Yes/No):\n" + "\n".join(
                f"- {b['symbol']} {b['price']:,.2f}: stop {b['stop']:,.2f}, target {b['target']:,.2f}, RSI {b['rsi']:.0f}"
                for b in best)
        m = re.search(r"\b(?:analy[sz]e|check|chart|look at)\s+" + SYMBOL, t, re.I)
        if m:
            return analyse(m.group(1))
    except RuntimeError as exc:
        return str(exc)
    if low.startswith("/trade"):
        return __doc__.split("Commands", 1)[1].split("Data:", 1)[0].strip()
    return None


if __name__ == "__main__":
    import sys
    print(handle(" ".join(sys.argv[1:]) or "analyse BHP.AX") or "Try: analyse BHP.AX")


# ==========================================
# SCAN, PROPOSE, APPROVE, PLACE (with your Yes on Telegram)
# ==========================================

WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AMD", "TSLA",
             "AVGO", "NFLX", "JPM", "V", "COST"]
PENDING = DIR / "pending.json"
PENDING_MINUTES = 60


def setup_for(symbol):
    """A pullback-in-an-uptrend setup, or None. Returns plan + rows for the chart."""
    rows, meta = candles(symbol)
    closes = [r[4] for r in rows]
    price = float(meta.get("regularMarketPrice") or closes[-1])
    s20, s50, r, a = sma(closes, 20), sma(closes, 50), rsi(closes), atr(rows)
    if not (price > s20 > s50 and 40 <= r <= 65):
        return None
    dist = (price - s20) / a  # how far above the 20-day average, in daily ranges
    if dist > 1.2:
        return None  # too stretched; wait for a pullback
    strength = (s20 / s50 - 1) * 100
    score = strength * 2 - dist * 3 - abs(r - 52) / 5
    stop, target = price - 1.5 * a, price + 3 * a
    return {"symbol": symbol, "price": price, "stop": stop, "target": target, "rsi": r, "atr": a,
            "sma20": s20, "sma50": s50, "score": score, "rows": rows,
            "why": (f"Uptrend (20-day avg {s20:,.2f} above 50-day {s50:,.2f}), pulled back near the 20-day "
                    f"average, RSI {r:.0f} (not overbought). Stop 1.5× daily range below, target 2× the risk.")}


def scan(watchlist=None, top=2):
    found = []
    for sym in watchlist or WATCHLIST:
        try:
            s = setup_for(sym)
        except RuntimeError:
            continue
        if s:
            found.append(s)
    return sorted(found, key=lambda s: s["score"], reverse=True)[:top]


def size_for(s):
    import echo_broker
    equity = account_value()
    if echo_broker.is_configured():
        try:
            equity = echo_broker.account()["equity"]
        except RuntimeError:
            pass
    risk = equity * RISK_PER_TRADE
    qty = max(1, math.floor(risk / max(s["price"] - s["stop"], 1e-9)))
    qty = min(qty, math.floor(equity * .25 / s["price"]) or 1)  # never more than 25% of the account in one trade
    return qty, risk, equity


def propose(s):
    """Save a pending trade and return (message, chart PNG bytes)."""
    import echo_broker
    import echo_chart
    qty, risk, equity = size_for(s)
    plan = {"symbol": s["symbol"], "qty": qty, "entry": s["price"], "stop": round(s["stop"], 2),
            "target": round(s["target"], 2), "created": datetime.now(timezone.utc).isoformat()}
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    where = ("your " + echo_broker.mode() + " broker account") if echo_broker.is_configured() \
        else "Echo's paper journal (no broker connected yet)"
    msg = "\n".join([
        f"TRADE IDEA: BUY {qty} {s['symbol']} @ about {s['price']:,.2f}",
        f"Stop-loss {plan['stop']:,.2f} · Target {plan['target']:,.2f} · Risk about ${risk:,.0f} "
        f"(1% of ${equity:,.0f})",
        s["why"],
        "",
        f"Tap ✅ Place trade to place it in {where}, or ❌ Skip trade. "
        f"This idea expires in {PENDING_MINUTES} minutes.",
        DISCLAIMER,
    ])
    png = echo_chart.candle_chart(s["rows"], s["price"], s["stop"], s["target"])
    return msg, png


def pending():
    try:
        plan = json.loads(PENDING.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(plan["created"])).total_seconds()
    if age > PENDING_MINUTES * 60:
        PENDING.unlink(missing_ok=True)
        return None
    return plan


def skip():
    PENDING.unlink(missing_ok=True)
    return "Skipped. No trade placed."


def approve():
    """You said yes: place the pending trade. Returns (message, chart PNG or None)."""
    import time as _time
    import echo_broker
    import echo_chart
    plan = pending()
    if not plan:
        return "That trade idea has expired or was already handled. Nothing was placed.", None
    PENDING.unlink(missing_ok=True)
    rows, _ = candles(plan["symbol"])
    if echo_broker.is_configured():
        order = echo_broker.place_bracket(plan["symbol"], plan["qty"], plan["stop"], plan["target"])
        status, fill = order.get("status", ""), None
        for _ in range(10):  # wait up to ~20 s for the fill
            _time.sleep(2)
            o = echo_broker.order_status(order["id"])
            status = o.get("status", status)
            if o.get("filled_avg_price"):
                fill = float(o["filled_avg_price"])
                break
        entry = fill or plan["entry"]
        msg = (f"✅ ORDER PLACED ({echo_broker.mode()}): BUY {plan['qty']} {plan['symbol']}"
               f"{' filled at ' + format(fill, ',.2f') if fill else ' (status: ' + status + ', fills at market open if closed)'}\n"
               f"Stop-loss {plan['stop']:,.2f} and take-profit {plan['target']:,.2f} are attached.\n"
               f"Order ID {order['id']}")
    else:
        msg = paper_buy(plan["symbol"], plan["qty"]) + (
            f"\nPlan: stop {plan['stop']:,.2f}, target {plan['target']:,.2f}. "
            "Connect a broker (TRADING_SETUP.md) for real orders with automatic stops.")
        entry = plan["entry"]
    png = echo_chart.candle_chart(rows, entry, plan["stop"], plan["target"], mark_last=True)
    return msg, png


def scan_and_propose():
    """Find the best setup and return (message, png) for it, or (message, None)."""
    best = scan(top=1)
    if not best:
        return ("Scanned " + str(len(WATCHLIST)) + " stocks: no setup good enough today. "
                "Sitting out is a valid trade."), None
    return propose(best[0])


# ==========================================
# PHONE (Telegram): picture + Place trade / Skip trade buttons
# ==========================================

TRADE_KEYBOARD = json.dumps({"keyboard": [["✅ Place trade", "❌ Skip trade"]],
                             "one_time_keyboard": True, "resize_keyboard": True})
SCAN_TIME = "19:30"  # Adelaide time: approve in the evening, US orders fill at the 1 AM open


def _telegram_photo(png, caption):
    from echo_telegram import chat_bot_credentials
    token, chat = chat_bot_credentials()
    if not (token and chat):
        return False
    boundary = "EchoTradeBoundary42"
    parts = []
    for name, value in (("chat_id", chat), ("caption", caption[:1000])):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="trade.png"\r\n'
                  "Content-Type: image/png\r\n\r\n").encode() + png + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendPhoto", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("ok", False)


def _telegram_text(text, keyboard=None):
    from echo_telegram import chat_bot_credentials
    token, chat = chat_bot_credentials()
    params = {"chat_id": chat, "text": text[:4000]}
    if keyboard:
        params["reply_markup"] = keyboard
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                 data=urllib.parse.urlencode(params).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("ok", False)


def send_idea_to_phone():
    """Scan, and send the best idea with a chart and Place/Skip buttons."""
    msg, png = scan_and_propose()
    if png:
        p = pending() or {}
        _telegram_photo(png, f"{p.get('symbol', '')} · blue = entry, red = stop-loss, green = target")
        _telegram_text(msg, TRADE_KEYBOARD)
    else:
        _telegram_text(msg)
    return msg
