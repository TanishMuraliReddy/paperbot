"""
Strategy definitions — Python port of the JS STRATEGIES object.
Each strategy exposes a `signal(candles)` function returning
{signal: -1|0|1, ...meta}.
"""
from typing import List, Dict, Any

from indicators import (
    calc_ut_bot, calc_macd, calc_rsi, calc_bb, calc_atr,
    calc_adx, calc_ofi, classify_regime, calc_momentum_score,
)


def _signal_ut_macd_rsi(candles: List[Dict]) -> Dict:
    if len(candles) < 40:
        return {"signal": 0}
    closes = [c["close"] for c in candles]
    ut = calc_ut_bot(candles)
    macd = calc_macd(closes)
    rsi = calc_rsi(closes)
    if not ut or not macd or rsi is None:
        return {"signal": 0}
    if ut["flip"] and ut["dir"] == 1 and macd["bullCross"] and rsi < 70:
        return {"signal": 1}
    if ut["flip"] and ut["dir"] == -1 and macd["bearCross"] and rsi > 30:
        return {"signal": -1}
    return {"signal": 0}


def _signal_macd_bb(candles: List[Dict]) -> Dict:
    if len(candles) < 30:
        return {"signal": 0}
    closes = [c["close"] for c in candles]
    macd = calc_macd(closes)
    bb = calc_bb(closes)
    if not macd or not bb:
        return {"signal": 0}
    price = closes[-1]
    if macd["bullCross"] and price < bb["mid"]:
        return {"signal": 1}
    if macd["bearCross"] and price > bb["mid"]:
        return {"signal": -1}
    return {"signal": 0}


def _signal_phantom(candles: List[Dict]) -> Dict:
    if len(candles) < 50:
        return {"signal": 0, "regime": "warming up", "score": None}
    closes = [c["close"] for c in candles]
    regime = classify_regime(candles, closes)
    ofi = calc_ofi(candles)
    score = calc_momentum_score(closes)
    adx = calc_adx(candles)
    bb = calc_bb(closes)
    macd = calc_macd(closes)
    rsi = calc_rsi(closes)
    atr = calc_atr(candles)
    if not all([score is not None, adx, bb, macd, rsi is not None, atr]):
        return {"signal": 0, "regime": regime, "score": score}
    price = closes[-1]
    signal = 0
    if regime == "volatile":
        return {"signal": 0, "regime": regime, "score": score, "ofi": ofi, "adx": adx["adx"]}
    if (regime in ("trending_up", "neutral") and score > 62 and ofi > 0.1
            and macd["macd"] > macd["signal"] and 40 < rsi < 75
            and price > bb["mid"] and adx["adx"] > 15):
        signal = 1
    if (regime in ("ranging", "neutral") and price < bb["lower"] * 1.008
            and ofi > -0.05 and rsi < 38
            and (macd["histogram"] > 0 or macd["bullCross"])):
        signal = 1
    if regime == "trending_down" and score < 38 and ofi < -0.1:
        signal = -1
    if score < 30 and ofi < -0.2:
        signal = -1
    return {
        "signal": signal,
        "regime": regime,
        "score": score,
        "ofi": round(ofi, 3),
        "adx": round(adx["adx"], 1),
        "rsi": rsi,
    }


STRATEGIES = [
    {
        "key": "UT+MACD+RSI",
        "name": "UT Bot + MACD + RSI",
        "tag": "MOMENTUM",
        "color": "#00d4ff",
        "desc": "ATR trailing stop · MACD crossover · RSI filter",
        "isPhantom": False,
        "signal": _signal_ut_macd_rsi,
    },
    {
        "key": "MACD+BB",
        "name": "MACD + Bollinger",
        "tag": "CROSSOVER",
        "color": "#ff9500",
        "desc": "MACD crossover confirmed by Bollinger Band position",
        "isPhantom": False,
        "signal": _signal_macd_bb,
    },
    {
        "key": "PHANTOM",
        "name": "PHANTOM",
        "tag": "REGIME·AI",
        "color": "#b044ff",
        "desc": "Regime-aware · Order flow · Adaptive momentum · Smart exits",
        "isPhantom": True,
        "signal": _signal_phantom,
    },
]
