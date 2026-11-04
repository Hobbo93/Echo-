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
  put $500 into AAPL    a trade with your money amount: Echo buys, then sells for you at
                        the stop-loss or target (one Yes from you to start it)
  sell AAPL             sell that position now (asks Yes/No first)
  /trade propose        top idea with a chart; tap Place trade (your approval) to place it
  market                UP / DOWN / WAIT for every stock on the watchlist
  venue trench          send Trench tickets + close alerts (or: venue alpaca / venue paper)
  bankroll 500          your Trench bankroll; each ticket stakes 2% of it
  open trades           Trench trades Echo is watching
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
    call, *_x, call_why = read_direction(rows, price)
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
        f"Call: {'🟢 UP' if call == 'UP' else '🔴 DOWN' if call == 'DOWN' else '⚪ WAIT'} ({call_why})",
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
        return trench_stats() or "No closed trades yet. Try: /trade propose"
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
    ] + ([trench_stats()] if trench_stats() else []))


# ==========================================
# COMMANDS
# ==========================================

SYMBOL = r"([A-Za-z0-9.\-^=]{1,15})"


def handle(text):
    """Run a trading command. Returns a reply, or None if it isn't one."""
    t = text.strip()
    low = t.lower()
    if STOP_RE.match(t):
        return stop_trading()
    if RESUME_RE.match(t):
        return resume_trading()
    if SELL_ALL_RE.match(t):
        return sell_all_request()
    try:
        m = re.search(r"\b(?:put|invest|buy|spend|trade)\s+\$\s?([\d,]+(?:\.\d+)?)\s*(?:aud|usd|dollars)?\s*"
                      r"(?:in|into|on|of|worth of)?\s+" + SYMBOL, t, re.I)
        if m:
            return amount_trade(m.group(2), float(m.group(1).replace(",", "")))
        m = re.match(r"^(?:/trade\s+)?(?:sell|close)\s+(?:all\s+(?:of\s+)?(?:my\s+)?)?" + SYMBOL + r"\s*$", t, re.I)
        if m and m.group(1).lower() not in ("trade", "it", "everything", "position"):
            return sell_request(m.group(1))
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
        if re.search(r"\b(market|up or down|overview)\b", low) and not re.search(r"\banaly", low):
            return market_overview()
        m = re.search(r"\bvenue\s+(trench|alpaca|broker|paper)\b", low)
        if m:
            st = settings()
            st["venue"] = "alpaca" if m.group(1) in ("alpaca", "broker") else m.group(1)
            save_settings(st)
            return "Trade venue set to " + st["venue"] + "."
        m = re.search(r"\bbankroll\s+\$?([\d,.]+)", low)
        if m:
            st = settings()
            st["trench_bankroll"] = float(m.group(1).replace(",", ""))
            save_settings(st)
            return (f"Trench bankroll set to ${st['trench_bankroll']:,.0f}. Each ticket stakes "
                    f"{st['trench_risk_pct']:g}% of it (${st['trench_bankroll'] * st['trench_risk_pct'] / 100:,.2f}).")
        if re.search(r"\b(open trades|trench trades)\b", low):
            open_t = [t for t in _load().get("trench", []) if t["status"] == "open"]
            return ("Open Trench trades Echo is watching:\n" + "\n".join(
                f"- {t['symbol']}: stop {t['stop']:,.2f}, target {t['target']:,.2f}, stake ${t['stake']:,.2f}"
                for t in open_t)) if open_t else "No open Trench trades."
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


def read_direction(rows, price):
    """UP, DOWN or WAIT with the numbers behind it."""
    closes = [r[4] for r in rows]
    s20, s50, r, a = sma(closes, 20), sma(closes, 50), rsi(closes), atr(rows)
    dist = (price - s20) / a
    if price > s20 > s50 and 40 <= r <= 65 and dist <= 1.2:
        return "UP", s20, s50, r, a, f"uptrend, dipped near the 20-day average, RSI {r:.0f}"
    if price < s20 < s50 and 35 <= r <= 60 and dist >= -1.2:
        return "DOWN", s20, s50, r, a, f"downtrend, bounced up near the 20-day average, RSI {r:.0f}"
    if price > s20 > s50:
        why = "uptrend but stretched, wait for a dip" if dist > 1.2 or r > 65 else "uptrend, no clean entry"
    elif price < s20 < s50:
        why = "downtrend but already oversold, wait for a bounce" if dist < -1.2 or r < 35 else "downtrend, no clean entry"
    else:
        why = "no clear trend"
    return "WAIT", s20, s50, r, a, why


def setup_for(symbol, allow_down=False):
    """An UP (or DOWN) setup, or None. Returns plan + rows for the chart."""
    rows, meta = candles(symbol)
    closes = [r[4] for r in rows]
    price = float(meta.get("regularMarketPrice") or closes[-1])
    direction, s20, s50, r, a, why = read_direction(rows, price)
    if direction == "WAIT" or (direction == "DOWN" and not allow_down):
        return None
    sign = 1 if direction == "UP" else -1
    strength = abs(s20 / s50 - 1) * 100
    score = strength * 2 - abs(price - s20) / a * 3 - abs(r - 50) / 5
    return {"symbol": symbol, "direction": direction, "price": price, "stop": price - sign * 1.5 * a,
            "target": price + sign * 3 * a, "rsi": r, "atr": a, "sma20": s20, "sma50": s50,
            "score": score, "rows": rows,
            "why": (f"{why.capitalize()} (20-day avg {s20:,.2f}, 50-day {s50:,.2f}). "
                    "Stop 1.5× daily range away, target 2× the risk.")}


def market_overview(watchlist=None):
    """Plain-language UP / DOWN / WAIT for every stock on the watchlist."""
    lines = ["📊 MARKET NOW (UP = go up, DOWN = go down, WAIT = no edge)"]
    for sym in watchlist or WATCHLIST:
        try:
            rows, meta = candles(sym)
            price = float(meta.get("regularMarketPrice") or rows[-1][4])
            d, *_rest, why = read_direction(rows, price)
            change = (rows[-1][4] / rows[-6][4] - 1) * 100
        except RuntimeError:
            continue
        icon = {"UP": "🟢 UP  ", "DOWN": "🔴 DOWN", "WAIT": "⚪ WAIT"}[d]
        lines.append(f"{icon} {sym} {price:,.2f} ({change:+.1f}% 5d): {why}")
    lines += ["", "Send /trade propose for the best one as a ticket with a chart.", DISCLAIMER]
    return "\n".join(lines)


def scan(watchlist=None, top=2):
    found = []
    allow_down = settings()["venue"] == "trench"
    for sym in watchlist or WATCHLIST:
        try:
            s = setup_for(sym, allow_down)
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
    qty = max(1, math.floor(risk / max(abs(s["price"] - s["stop"]), 1e-9)))
    qty = min(qty, math.floor(equity * .25 / s["price"]) or 1)  # never more than 25% of the account in one trade
    return qty, risk, equity


def propose(s):
    """Save a pending trade and return (message, chart PNG bytes)."""
    import echo_broker
    import echo_chart
    if is_paused():
        return PAUSED_MSG, None
    qty, risk, equity = size_for(s)
    plan = {"symbol": s["symbol"], "direction": s.get("direction", "UP"), "qty": qty, "entry": s["price"],
            "stop": round(s["stop"], 2),
            "target": round(s["target"], 2), "created": datetime.now(timezone.utc).isoformat()}
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    venue = settings()["venue"]
    if venue == "trench":
        where = "a Trench ticket (you place it on trench.io; Echo watches the price for you)"
    elif echo_broker.is_configured():
        where = "your " + echo_broker.mode() + " broker account"
    else:
        where = "Echo's paper journal (no broker connected yet)"
    msg = "\n".join([
        (f"TRADE IDEA: {s['symbol']} {'⬆️ UP' if plan['direction'] == 'UP' else '⬇️ DOWN'} @ about {s['price']:,.2f}"
         if venue == "trench" else f"TRADE IDEA: BUY {qty} {s['symbol']} @ about {s['price']:,.2f}"),
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


sent_to_phone = [False]  # True when the last trade ticket already went to Telegram
AMOUNT_RE = re.compile(r"\b(?:put|invest|buy|spend|trade)\s+\$\s?[\d,]+", re.I)
SELL_RE = re.compile(r"^(?:/trade\s+)?(?:sell|close)\s+(?:all\s+(?:of\s+)?(?:my\s+)?)?[A-Za-z0-9.\-^=]{1,15}\s*$", re.I)


def amount_trade(symbol, amount):
    """You choose the stock and how much money. Echo plans the buy, stop-loss and target,
    and asks Yes/No. After a Yes it buys, then sells for you when the stop or target hits."""
    import echo_broker
    import echo_chart
    if is_paused():
        return PAUSED_MSG
    symbol = symbol.upper()
    rows, meta = candles(symbol)
    price = float(meta.get("regularMarketPrice") or rows[-1][4])
    a = atr(rows)
    qty = math.floor(amount / price)
    if qty < 1:
        return f"${amount:,.2f} isn't enough for one {symbol} share (about {price:,.2f} each). Try a bigger amount."
    stop, target = round(price - 1.5 * a, 2), round(price + 3 * a, 2)
    sent_to_phone[0] = False
    direction, *_rest, why = read_direction(rows, price)
    plan = {"symbol": symbol, "direction": "UP", "qty": qty, "entry": price, "stop": stop, "target": target,
            "amount": amount, "venue": "broker", "side": "buy", "created": datetime.now(timezone.utc).isoformat()}
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    where = (("your " + echo_broker.mode() + " Alpaca account") if echo_broker.is_configured()
             else "Echo's practice account (connect Alpaca for real orders: double-click connect_echo.bat)")
    warn = "" if direction == "UP" else f"\n⚠️ Heads up: the chart says {direction} right now ({why}). Buying now goes against it."
    msg = "\n".join([
        f"YOUR TRADE: BUY {qty} {symbol} @ about {price:,.2f} = about ${qty * price:,.2f} of your ${amount:,.0f}",
        f"Echo sells for you automatically: at {target:,.2f} to take profit (+${(target - price) * qty:,.0f}) "
        f"or at {stop:,.2f} to cut the loss (-${(price - stop) * qty:,.0f}).",
        f"Placed in {where}.{warn}",
        "",
        f"Reply Yes to place it, or No to cancel. Expires in {PENDING_MINUTES} minutes.",
        DISCLAIMER,
    ])
    try:
        png = echo_chart.candle_chart(rows, price, stop, target)
        _telegram_photo(png, f"{symbol}: blue = buy, red = stop-loss, green = take profit")
        sent_to_phone[0] = bool(_telegram_text(msg, TRADE_KEYBOARD))
    except Exception:
        pass
    return msg


def sell_request(symbol):
    """Ask Yes/No before selling a whole position now."""
    import echo_broker
    symbol = symbol.upper()
    held = None
    if echo_broker.is_configured():
        try:
            held = next((p for p in echo_broker.positions() if p.get("symbol") == symbol), None)
            held = held and {"qty": float(held["qty"]), "entry": float(held["avg_entry_price"])}
        except RuntimeError as exc:
            return str(exc)
    else:
        held = _load()["positions"].get(symbol)
    if not held:
        return f"You don't hold any {symbol} right now."
    sent_to_phone[0] = False
    price, _ = live_price(symbol)
    pnl = (price - held["entry"]) * held["qty"]
    plan = {"symbol": symbol, "side": "sell", "qty": held["qty"], "entry": price, "venue": "broker",
            "created": datetime.now(timezone.utc).isoformat()}
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    msg = (f"SELL {held['qty']:g} {symbol} now @ about {price:,.2f}? That's {'a profit' if pnl >= 0 else 'a loss'} "
           f"of about {pnl:+,.2f}.\nReply Yes to sell, or No to keep it.")
    try:
        sent_to_phone[0] = bool(_telegram_text(msg, TRADE_KEYBOARD))
    except Exception:
        pass
    return msg


def check_paper_exits():
    """Practice account: sell automatically when a trade's stop-loss or target is hit."""
    j = _load()
    exits = j.get("exits", {})
    said = []
    for sym in [k for k in exits if k not in j["positions"]]:
        exits.pop(sym)
    _save(j)
    for sym, plan in list(exits.items()):
        try:
            price, _ = live_price(sym)
        except RuntimeError:
            continue
        if price >= plan["target"] or price <= plan["stop"]:
            hit = "target ✅" if price >= plan["target"] else "stop-loss 🛑"
            said.append(f"Echo sold {sym} at the {hit}: " + paper_sell(sym))
            j = _load()
            j.setdefault("exits", {}).pop(sym, None)
            _save(j)
    if said:
        try:
            _telegram_text("\n".join(said))
        except Exception:
            pass
    return said


# ==========================================
# STOP BUTTON: "Echo, stop trading" pauses everything at once
# ==========================================

STOP_RE = re.compile(r"^\s*(?:hey\s+)?(?:echo,?\s+)?(?:please\s+)?(?:/stoptrading\b|(?:stop|pause|halt|kill|freeze)\s+"
                     r"(?:all\s+)?(?:the\s+|my\s+)?(?:trading|trades|day ?trading)\b)", re.I)
RESUME_RE = re.compile(r"^\s*(?:hey\s+)?(?:echo,?\s+)?(?:please\s+)?(?:/resumetrading\b|(?:resume|restart|unpause|start)\s+"
                       r"(?:the\s+|my\s+)?(?:trading|day ?trading)\b)", re.I)
SELL_ALL_RE = re.compile(r"^\s*(?:hey\s+)?(?:echo,?\s+)?(?:please\s+)?(?:/sellall\b.*|(?:sell|close)\s+(?:out\s+)?"
                         r"(?:everything|all(?:\s+(?:of\s+)?my)?(?:\s+(?:positions|trades|stocks|shares))?)\s*(?:now)?[.!]*)$", re.I)
PAUSED_MSG = "⏸️ Trading is paused (you said stop). Say \"resume trading\" to turn it back on."


def is_paused():
    return bool(settings().get("paused"))


def _holdings():
    """Everything open right now: (broker symbols, paper symbols, open Trench trades)."""
    import echo_broker
    broker = []
    if echo_broker.is_configured():
        try:
            broker = [p["symbol"] for p in echo_broker.positions()]
        except Exception:
            broker = ["(couldn't check the broker)"]
    j = _load()
    trench = [t["symbol"] for t in j.get("trench", []) if t.get("status") == "open"]
    return broker, list(j["positions"]), trench


def _holdings_text(broker, paper, trench):
    lines = []
    if broker:
        lines.append("Broker: " + ", ".join(broker))
    if paper:
        lines.append("Practice account: " + ", ".join(paper))
    if trench:
        lines.append("Trench (you close these on trench.io): " + ", ".join(trench))
    return "\n".join(lines)


def stop_trading():
    """Pause at once: no new ideas, no new buys, any waiting trade cancelled. Open trades keep their
    stop-loss and target, so they stay protected. Selling them is a separate step."""
    s = settings()
    s["paused"] = True
    s["paused_at"] = datetime.now(timezone.utc).isoformat()
    save_settings(s)
    waiting = pending()
    PENDING.unlink(missing_ok=True)
    broker, paper, trench = _holdings()
    msg = "🛑 Trading stopped. No new trade ideas and no new buys until you say \"resume trading\"."
    if waiting and waiting.get("side") != "sell":
        msg += f"\nThe waiting {waiting.get('symbol', '')} trade idea was cancelled."
    held = _holdings_text(broker, paper, trench)
    if held:
        msg += ("\n\nStill open (their stop-loss and target still protect them):\n" + held +
                "\n\nTo sell them all now, say \"sell everything\".")
    else:
        msg += "\nNothing is open."
    return msg


def resume_trading():
    s = settings()
    s["paused"] = False
    save_settings(s)
    return "▶️ Trading is back on. Trade ideas will come again, and every trade still needs your Yes."


def sell_all_request():
    """Ask Yes/No before selling every open position."""
    broker, paper, trench = _holdings()
    broker = [b for b in broker if not b.startswith("(")]
    if not broker and not paper:
        extra = "\nOpen on Trench (close these on trench.io yourself): " + ", ".join(trench) if trench else ""
        return "Nothing to sell: there are no open positions." + extra
    plan = {"side": "sell_all", "broker": broker, "paper": paper, "symbol": "everything",
            "created": datetime.now(timezone.utc).isoformat()}
    DIR.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(json.dumps(plan), encoding="utf-8")
    return ("⚠️ Sell EVERYTHING now at market price?\n" + _holdings_text(broker, paper, []) +
            ("\n(Trench trades can't be closed by Echo: close them on trench.io.)" if trench else "") +
            "\n\nReply Yes to sell it all, or No to keep them.")


def sell_everything(plan):
    import echo_broker
    lines = []
    if plan.get("broker"):
        try:
            echo_broker.close_all()
            lines.append(f"✅ Broker ({echo_broker.mode()}): sold {', '.join(plan['broker'])} and cancelled their orders.")
        except Exception as exc:
            lines.append(f"❌ Broker: NOT sold ({str(exc)[:200]}). Check your Alpaca account.")
    for sym in plan.get("paper", []):
        try:
            lines.append(paper_sell(sym))
        except Exception as exc:
            lines.append(f"❌ {sym} (practice): NOT sold ({str(exc)[:120]})")
    return "\n".join(lines) or "Nothing was open."


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
    if plan.get("side") == "sell_all":
        return sell_everything(plan), None
    if plan.get("side") != "sell" and is_paused():
        return PAUSED_MSG + " Nothing was bought.", None
    if plan.get("side") == "sell":
        if echo_broker.is_configured():
            order = echo_broker.close_position(plan["symbol"])
            return (f"✅ SOLD ({echo_broker.mode()}): {plan['qty']:g} {plan['symbol']} at market. "
                    f"Order ID {order.get('id', '')}"), None
        return paper_sell(plan["symbol"]), None
    rows, _ = candles(plan["symbol"])
    if plan.get("venue", settings()["venue"]) == "trench":
        stake, _pct, mult, msg = trench_ticket(plan)
        _open_trench_trade(plan, stake, mult)
        png = echo_chart.candle_chart(rows, plan["entry"], plan["stop"], plan["target"], mark_last=True)
        return msg, png
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
            f"\nEcho will sell it for you at the stop {plan['stop']:,.2f} or the target {plan['target']:,.2f}. "
            "Connect Alpaca (double-click connect_echo.bat) for real orders.")
        j = _load()
        if plan["symbol"] in j["positions"]:
            j.setdefault("exits", {})[plan["symbol"]] = {"stop": plan["stop"], "target": plan["target"]}
            _save(j)
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
    if is_paused():
        return "Trading is paused, so no trade idea was sent."
    msg, png = scan_and_propose()
    if png:
        p = pending() or {}
        _telegram_photo(png, f"{p.get('symbol', '')} · blue = entry, red = stop-loss, green = target")
        _telegram_text(msg, TRADE_KEYBOARD)
    else:
        _telegram_text(msg)
    return msg


# ==========================================
# TRENCH MODE: Echo researches and sends a ticket, you place it on trench.io,
# Echo watches the price and tells you when to close.
# (Trench has no public API, so Echo never clicks trades there for you.)
# ==========================================

SETTINGS = DIR / "settings.json"
TRENCH_URL = "https://trench.io"


def settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        s = {}
    s.setdefault("venue", "trench")
    s.setdefault("trench_bankroll", 500.0)
    s.setdefault("trench_risk_pct", 2.0)  # stake per trade as % of bankroll (the stake can be lost in full)
    return s


def save_settings(s):
    DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def trench_ticket(plan):
    s = settings()
    stake = max(1.0, round(s["trench_bankroll"] * s["trench_risk_pct"] / 100, 2))
    up = plan.get("direction", "UP") == "UP"
    stop_pct = abs(plan["entry"] - plan["stop"]) / plan["entry"] * 100
    safe_mult = max(1, min(10, int(80 / max(stop_pct, .1))))  # keep a stop-loss move well short of wiping the stake
    return stake, stop_pct, safe_mult, "\n".join([
        f"🎯 TRENCH TICKET: {plan['symbol']} {'⬆️ UP' if up else '⬇️ DOWN'}",
        f"Stake: ${stake:,.2f} ({s['trench_risk_pct']:g}% of your ${s['trench_bankroll']:,.0f} Trench bankroll)",
        f"Multiplier: {safe_mult}x or lower. Higher multipliers can wipe the stake on normal daily wiggles.",
        f"Entry around {plan['entry']:,.2f}",
        (f"Close it if the price drops to {plan['stop']:,.2f} ({stop_pct:.1f}% against you), or rises to {plan['target']:,.2f}."
         if up else f"Close it if the price rises to {plan['stop']:,.2f} ({stop_pct:.1f}% against you), or falls to {plan['target']:,.2f}."),
        "Echo is now watching the price and will text you when to close.",
        f"Open Trench: {TRENCH_URL}",
        "Assume you can lose the whole stake. Education, not financial advice.",
    ])


def _open_trench_trade(plan, stake, mult):
    j = _load()
    j.setdefault("trench", []).append({**plan, "stake": stake, "multiplier": mult, "status": "open",
                                       "opened": datetime.now(timezone.utc).isoformat()})
    _save(j)


def check_trench_trades():
    """Return alert messages for open Trench trades that hit their stop or target."""
    j = _load()
    alerts = []
    changed = False
    for t in j.get("trench", []):
        if t["status"] != "open":
            continue
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(t["opened"])).days
        try:
            price, _ = live_price(t["symbol"])
        except RuntimeError:
            continue
        up = t.get("direction", "UP") == "UP"
        hit_stop = price <= t["stop"] if up else price >= t["stop"]
        hit_target = price >= t["target"] if up else price <= t["target"]
        if hit_stop:
            t.update(status="loss", exit=price)
            alerts.append(f"🔴 CLOSE {t['symbol']} ON TRENCH NOW: price {price:,.2f} hit your stop-loss "
                          f"{t['stop']:,.2f}. Small losses are part of the plan. {TRENCH_URL}")
        elif hit_target:
            t.update(status="win", exit=price)
            alerts.append(f"🟢 TAKE PROFIT on {t['symbol']} ON TRENCH: price {price:,.2f} reached your target "
                          f"{t['target']:,.2f}. {TRENCH_URL}")
        elif age_days >= 10:
            t.update(status="expired", exit=price)
            alerts.append(f"⏱ {t['symbol']} on Trench hasn't hit its stop or target in 10 days (now {price:,.2f}). "
                          "Consider closing it.")
        else:
            continue
        changed = True
    if changed:
        _save(j)
    return alerts


def trench_stats():
    done = [t for t in _load().get("trench", []) if t["status"] in ("win", "loss")]
    if not done:
        return ""
    wins = sum(t["status"] == "win" for t in done)
    return f"Trench ideas: {len(done)} closed, {wins} hit target ({wins / len(done) * 100:.0f}% win rate)."
