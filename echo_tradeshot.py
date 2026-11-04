"""Send Echo a screenshot of a chart and the Trading Analyst tells you what it sees and what to do.

On Telegram, send the screenshot with a caption like "what do I do?", "NVDA", "should I buy this"
(or send it to the Trading Analyst / Day Trading Desk in Echo HQ).

1. The free vision model on your PC reads the screenshot: which stock, rough price, timeframe.
   If you put the ticker in the caption ("TSLA"), Echo uses that instead.
2. Echo runs its real analysis on that stock (live prices: trend, momentum, support and
   resistance, and a risk plan with entry, stop-loss and target).
3. You get the plan back, plus Echo's own chart of that stock with the entry (blue), stop-loss
   (red) and target (green) drawn on it.

It never places a trade. Education, not financial advice. Free, nothing to pay for.
"""
import json
import re

import echo_photos
import echo_trading

TRADE_WORDS = re.compile(r"\b(trade|trading|chart|stock|share|ticker|candles?|buy|sell|long|short|entry|stop|"
                         r"target|what (do|should) i do|setup|breakout|support|resistance|crypto|forex|gold|day ?trad\w*)\b",
                         re.I)
_TICKER = re.compile(r"(?:\$|\b)([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")
_NOT_TICKERS = {"I", "A", "AM", "PM", "OK", "MY", "ME", "DO", "IS", "IT", "TO", "THE", "AND", "WHAT", "BUY", "SELL",
                "NOW", "ECHO", "USD", "AUD", "RSI", "ATR", "SMA", "EMA", "MACD", "VWAP", "HOD", "LOD", "ATH", "PLS"}

READ_PROMPT = (
    "This is a screenshot from a trading app or chart. Read it carefully and answer with ONLY a JSON object: "
    '{"symbol": the stock/crypto ticker shown (e.g. "NVDA", "BTC-USD") or null if you can\'t read one, '
    '"price": the current price shown as a number or null, "timeframe": e.g. "5m", "1D" or null, '
    '"what_i_see": one or two short sentences about what the chart shows (trend, big moves, indicators)}. '
    "Only report what you can actually read. Don't guess a ticker."
)


def wants_trade_read(caption, employee=""):
    caption = (caption or "").strip()
    if re.search(r"trading|day trading desk", employee or "", re.I):
        return True
    return bool(TRADE_WORDS.search(caption) or re.fullmatch(r"\$?[A-Za-z]{1,5}(\.[A-Za-z]{1,2})?\??", caption))


def ticker_from_caption(caption):
    for raw in _TICKER.findall(caption or ""):
        if raw not in _NOT_TICKERS:
            return raw
    m = re.fullmatch(r"\s*\$?([A-Za-z]{1,5}(?:\.[A-Za-z]{1,2})?)\??\s*", caption or "")
    if m and m.group(1).upper() not in _NOT_TICKERS:
        return m.group(1).upper()
    return None


def _parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def read(image, caption="", look=None):
    """What the screenshot shows: {'symbol', 'price', 'timeframe', 'what_i_see'} (any may be missing)."""
    look = look or (lambda img, q: echo_photos.look([img], q))
    seen = _parse(look(image, READ_PROMPT))
    sym = ticker_from_caption(caption) or seen.get("symbol")
    if isinstance(sym, str):
        sym = sym.strip().upper().lstrip("$")
        if not re.fullmatch(r"[A-Z0-9.\-^=]{1,15}", sym):
            sym = None
    else:
        sym = None
    seen["symbol"] = sym
    return seen


def plan_chart(symbol):
    """Echo's own chart of the stock with entry, stop-loss and target (same rules as the analysis)."""
    import echo_chart
    rows, meta = echo_trading.candles(symbol)
    price = float(meta.get("regularMarketPrice") or rows[-1][4])
    a = echo_trading.atr(rows)
    return echo_chart.candle_chart(rows, price, price - 1.5 * a, price + 3 * a, mark_last=True)


def analyse_screenshot(image, caption="", look=None):
    """Returns (reply text, chart PNG bytes or None). Never raises."""
    if not echo_photos.has_vision() and not ticker_from_caption(caption):
        return ("To read chart screenshots I need the free photo brain on your PC. Send /getvision to download "
                "it. Or put the ticker in the caption (e.g. 'NVDA') and I'll analyse that stock straight away."), None
    seen = {}
    if echo_photos.has_vision():
        try:
            seen = read(image, caption, look)
        except Exception as exc:
            seen = {"symbol": ticker_from_caption(caption), "what_i_see": f"(I couldn't read the picture: {str(exc)[:120]})"}
    else:
        seen = {"symbol": ticker_from_caption(caption)}
    parts = ["📊 Trading Analyst"]
    if seen.get("what_i_see"):
        parts.append("What I see in your screenshot: " + str(seen["what_i_see"])[:400])
    sym = seen.get("symbol")
    if not sym:
        parts.append("\nI couldn't read which stock this is. Send it again with the ticker as the caption "
                     "(e.g. 'TSLA') and I'll give you a proper plan from live prices.")
        return "\n".join(parts), None
    try:
        analysis = echo_trading.analyse(sym)
    except Exception as exc:
        parts.append(f"\nI read the ticker as {sym}, but couldn't get its live prices ({str(exc)[:120]}). "
                     "If that's the wrong ticker, send the screenshot again with the right one as the caption.")
        return "\n".join(parts), None
    if seen.get("price"):
        parts.append(f"(Your screen shows about {seen['price']}; the plan below uses the latest live price.)")
    parts += ["", analysis, "",
              "On the chart I sent: blue = entry, red = stop-loss (get out if it hits), green = target.",
              "I never place trades from a screenshot. If you want to act on it, you decide."]
    try:
        png = plan_chart(sym)
    except Exception:
        png = None
    return "\n".join(parts), png
