"""
Indicator math — direct Python port of the JS calcEMA/RSI/ATR/MACD/BB/UTBot/ADX/ROC/OFI/Regime/Momentum.
All function signatures mirror the originals so strategies.py stays readable.
"""
import math
import random
from typing import List, Optional, Dict, Any


def calc_ema(arr: List[float], period: int) -> List[Optional[float]]:
    k = 2 / (period + 1)
    out: List[Optional[float]] = []
    for i in range(len(arr)):
        if i < period - 1:
            out.append(None)
        elif i == period - 1:
            out.append(sum(arr[:period]) / period)
        else:
            out.append(out[i - 1] * (1 - k) + arr[i] * k)
    return out


def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    ag = al = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        ag += max(0.0, d)
        al += max(0.0, -d)
    ag /= period
    al /= period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(0.0, d)) / period
        al = (al * (period - 1) + max(0.0, -d)) / period
    if al == 0:
        return 100.0
    return round(100 - 100 / (1 + ag / al), 2)


def calc_atr(candles: List[Dict], period: int = 14) -> Optional[float]:
    if len(candles) < period:
        return None
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            trs.append(max(
                c["high"] - c["low"],
                abs(c["high"] - candles[i - 1]["close"]),
                abs(c["low"] - candles[i - 1]["close"]),
            ))
    return sum(trs[-period:]) / period


def calc_macd(closes: List[float]) -> Optional[Dict]:
    if len(closes) < 35:
        return None
    fast = calc_ema(closes, 12)
    slow = calc_ema(closes, 26)
    macd_line = [
        (f - s) if f is not None and s is not None else None
        for f, s in zip(fast, slow)
    ]
    valid = [v for v in macd_line if v is not None]
    if len(valid) < 9:
        return None
    signal_line = calc_ema(valid, 9)
    m_val = macd_line[-1]
    s_val = signal_line[-1]
    m_prev = macd_line[-2] if len(macd_line) > 1 else None
    s_prev = signal_line[-2] if len(signal_line) > 1 else None
    if m_val is None or s_val is None:
        return None
    return {
        "macd": m_val,
        "signal": s_val,
        "histogram": m_val - s_val,
        "bullCross": m_val > s_val and m_prev is not None and s_prev is not None and m_prev <= s_prev,
        "bearCross": m_val < s_val and m_prev is not None and s_prev is not None and m_prev >= s_prev,
    }


def calc_bb(closes: List[float], period: int = 20, mult: float = 2.0) -> Optional[Dict]:
    if len(closes) < period:
        return None
    sl = closes[-period:]
    mean = sum(sl) / period
    std = math.sqrt(sum((v - mean) ** 2 for v in sl) / period)
    return {"upper": mean + mult * std, "lower": mean - mult * std, "mid": mean}


def calc_ut_bot(candles: List[Dict], sensitivity: float = 1.5) -> Optional[Dict]:
    if len(candles) < 16:
        return None
    atr = calc_atr(candles, 14)
    if not atr:
        return None
    n_loss = sensitivity * atr
    curr = candles[-1]["close"]
    prev = candles[-2]["close"]
    trail = prev
    if curr > trail:
        new_trail = max(trail, curr - n_loss)
        direction = 1
    else:
        new_trail = min(trail, curr + n_loss)
        direction = -1
    prev_dir = 1 if prev > trail else -1
    return {"trail": new_trail, "dir": direction, "flip": direction != prev_dir}


def calc_adx(candles: List[Dict], period: int = 14) -> Optional[Dict]:
    if len(candles) < period * 2:
        return None
    sl = candles[-(period * 2):]
    plus_dm, minus_dm, tr = [], [], []
    for i in range(1, len(sl)):
        c, p = sl[i], sl[i - 1]
        up = c["high"] - p["high"]
        down = p["low"] - c["low"]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr.append(max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"])))
    s_tr = sum(tr[-period:])
    if s_tr == 0:
        return None
    di_p = sum(plus_dm[-period:]) / s_tr * 100
    di_m = sum(minus_dm[-period:]) / s_tr * 100
    adx = 0.0 if (di_p + di_m) == 0 else abs(di_p - di_m) / (di_p + di_m) * 100
    return {"adx": round(adx, 2), "diPlus": di_p, "diMinus": di_m}


def calc_roc(closes: List[float], p: int) -> Optional[float]:
    if len(closes) < p + 1:
        return None
    return round((closes[-1] - closes[-p - 1]) / closes[-p - 1] * 100, 4)


def calc_ofi(candles: List[Dict]) -> float:
    if len(candles) < 5:
        return 0.0
    buy = sell = 0.0
    for c in candles[-5:]:
        rng = (c["high"] - c["low"]) or 0.0001
        body = abs(c["close"] - c["open"]) / rng
        wick = (min(c["open"], c["close"]) - c["low"] - (c["high"] - max(c["open"], c["close"]))) / rng
        vol = c.get("volume") or 1
        if c["close"] > c["open"]:
            buy += body * vol * (1 + wick)
        else:
            sell += body * vol * (1 - wick)
    t = buy + sell
    return 0.0 if t == 0 else round((buy - sell) / t, 4)


def classify_regime(candles: List[Dict], closes: List[float]) -> str:
    adx = calc_adx(candles)
    if not adx or len(candles) < 31:
        return "unknown"
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]

    def std(arr: List[float]) -> float:
        m = sum(arr) / len(arr)
        return math.sqrt(sum((v - m) ** 2 for v in arr) / len(arr))

    vr = std(rets[-10:]) / (std(rets[-30:]) or 0.0001)
    if vr > 1.8:
        return "volatile"
    if adx["adx"] > 25 and adx["diPlus"] > adx["diMinus"]:
        return "trending_up"
    if adx["adx"] > 25 and adx["diMinus"] > adx["diPlus"]:
        return "trending_down"
    if adx["adx"] < 20:
        return "ranging"
    return "neutral"


def calc_momentum_score(closes: List[float]) -> Optional[float]:
    r5 = calc_roc(closes, 5)
    r10 = calc_roc(closes, 10)
    r20 = calc_roc(closes, 20)
    rsi = calc_rsi(closes)
    if any(v is None for v in [r5, r10, r20, rsi]):
        return None

    def n(v: float, mn: float, mx: float) -> float:
        return max(0.0, min(1.0, (v - mn) / (mx - mn)))

    return round(
        (n(r5, -5, 5) * 0.4 + n(r10, -8, 8) * 0.3 + n(r20, -12, 12) * 0.2 + n(rsi, 0, 100) * 0.1) * 100,
        1,
    )


# ── Simulation fallback ──────────────────────────────────────────────────────
_sim_price = 85.65
_sim_tick = 0


def _gauss() -> float:
    u = v = 0.0
    while not u:
        u = random.random()
    while not v:
        v = random.random()
    return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)


def next_sim() -> float:
    global _sim_price, _sim_tick
    rb = (1.008 if random.random() > 0.5 else 0.993) if _sim_tick % 97 == 0 else 1.0
    sh = (1.015 if random.random() > 0.5 else 0.986) if _sim_tick % 43 == 0 else 1.0
    _sim_price = max(40.0, min(300.0, _sim_price * (1 + 0.00008 + 0.007 * _gauss()) * rb * sh))
    _sim_tick += 1
    return _sim_price
