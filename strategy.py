from math import isfinite

def ema(values, period):
    if len(values) < period: return None
    alpha = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]: result = value * alpha + result * (1-alpha)
    return result

def atr(candles, period=14):
    if len(candles) < period + 1: return None
    trs=[]
    for i in range(1, len(candles)):
        high, low, prev = candles[i][2], candles[i][3], candles[i-1][4]
        trs.append(max(high-low, abs(high-prev), abs(low-prev)))
    return sum(trs[-period:]) / period

def breakout_signal(raw_klines, lookback=20, stop_mult=1.5):
    # Binance kline rows: [openTime, open, high, low, close, volume, closeTime, ...].
    # Ignore the currently forming candle to avoid intrabar lookahead.
    if len(raw_klines) < max(lookback + 2, 30): return None
    c=[]
    for row in raw_klines:
        c.append([int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]), int(row[6])])
    closed = c[:-1]
    prior = closed[-lookback-1:-1]
    latest = closed[-1]
    closes=[x[4] for x in closed]
    fast, slow = ema(closes, 9), ema(closes, 21)
    volatility=atr(closed, 14)
    if not volatility or not fast or not slow or not isfinite(volatility) or volatility <= 0: return None
    upper=max(x[2] for x in prior); lower=min(x[3] for x in prior)
    # Confirm with EMA direction and close outside prior range; no claim this has positive expectancy.
    if latest[4] > upper and fast > slow:
        return {"side":"BUY", "entry":latest[4], "stop":latest[4]-stop_mult*volatility, "take":latest[4]+stop_mult*volatility*1.2, "bar_time":latest[0]}
    if latest[4] < lower and fast < slow:
        return {"side":"SELL", "entry":latest[4], "stop":latest[4]+stop_mult*volatility, "take":latest[4]-stop_mult*volatility*1.2, "bar_time":latest[0]}
    return None
