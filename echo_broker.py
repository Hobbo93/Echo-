"""Echo's broker connection (Alpaca). Places an order ONLY after you approve it.

Starts in PAPER mode (practice money). Real-money trading needs you to set
"alpaca_live": true in your Echo settings yourself (see TRADING_SETUP.md).
Every order is a bracket: entry + stop-loss + take-profit, so risk is capped
from the moment it's placed. US shares only (Alpaca doesn't do bracket orders
for crypto).
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path.home() / ".echo_telegram.json"


def _settings():
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    key = os.getenv("ALPACA_KEY_ID") or str(data.get("alpaca_key_id", "")).strip()
    secret = os.getenv("ALPACA_SECRET_KEY") or str(data.get("alpaca_secret_key", "")).strip()
    live = str(os.getenv("ALPACA_LIVE") or data.get("alpaca_live", "")).lower() in ("1", "true", "yes")
    return key, secret, live


def is_configured():
    key, secret, _ = _settings()
    return bool(key and secret)


def mode():
    return "LIVE (real money)" if _settings()[2] else "PAPER (practice money)"


def _api(method, path, body=None):
    key, secret, live = _settings()
    if not (key and secret):
        raise RuntimeError("No broker connected yet. See TRADING_SETUP.md to add your Alpaca keys.")
    base = "https://api.alpaca.markets" if live else "https://paper-api.alpaca.markets"
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None, method=method,
                                 headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Broker said no ({exc.code}): {detail}") from None
    except urllib.error.URLError:
        raise RuntimeError("Couldn't reach the broker. Check the internet connection.") from None


def account():
    a = _api("GET", "/v2/account")
    return {"equity": float(a.get("equity", 0)), "cash": float(a.get("cash", 0)),
            "buying_power": float(a.get("buying_power", 0)), "status": a.get("status", "")}


def place_bracket(symbol, qty, stop, target):
    """Market buy with attached stop-loss and take-profit."""
    order = _api("POST", "/v2/orders", {
        "symbol": symbol.upper(), "qty": str(int(qty)), "side": "buy", "type": "market",
        "time_in_force": "day", "order_class": "bracket",
        "take_profit": {"limit_price": f"{target:.2f}"},
        "stop_loss": {"stop_price": f"{stop:.2f}"},
    })
    return order


def order_status(order_id):
    return _api("GET", f"/v2/orders/{order_id}")


def positions():
    return _api("GET", "/v2/positions")


def close_all():
    """Sell every position at market and cancel all open stop/target orders."""
    return _api("DELETE", "/v2/positions?cancel_orders=true")


def close_position(symbol):
    """Sell the whole position now: cancels its open stop/target orders first, then sells at market."""
    symbol = symbol.upper()
    for o in _api("GET", "/v2/orders?status=open&nested=false&symbols=" + symbol) or []:
        try:
            _api("DELETE", "/v2/orders/" + o["id"])
        except RuntimeError:
            pass
    return _api("DELETE", "/v2/positions/" + symbol)
