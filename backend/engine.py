"""
Trading engine — runs 3 bots × 4 timeframes independently of any browser.
Connects to Kraken WebSocket; falls back to GBM simulation if unavailable.
"""
import asyncio
import json
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import websockets

from indicators import calc_atr, next_sim
from strategies import STRATEGIES

CAPITAL = 10_000.0
TIMEFRAMES = [
    {"key": "1m",  "label": "1 MIN",  "secs": 60,   "color": "#ff4488"},
    {"key": "5m",  "label": "5 MIN",  "secs": 300,  "color": "#ff9500"},
    {"key": "15m", "label": "15 MIN", "secs": 900,  "color": "#00d4ff"},
    {"key": "1h",  "label": "1 HOUR", "secs": 3600, "color": "#00ff88"},
]
TF_BY_KEY   = {t["key"]: t for t in TIMEFRAMES}
TF_INTERVAL = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}
KRAKEN_WS   = "wss://ws.kraken.com/v2"
KRAKEN_OHLC = "https://api.kraken.com/0/public/OHLC"


# ── State factories ──────────────────────────────────────────────────────────

def _mk_engine(tf_key: str) -> Dict:
    return {
        "tfKey": tf_key,
        "capital": CAPITAL,
        "cash": CAPITAL,
        "position": None,
        "trades": [],
        "equity": [{"t": int(time.time() * 1000), "v": CAPITAL}],
        "candles": [],
        "currentCandle": None,
        "lastSignal": 0,
        "lastMeta": {},
        "status": "warming up",
        "wins": 0,
        "losses": 0,
        "totalReturn": 0.0,
        "winRate": 0.0,
        "maxDrawdown": 0.0,
        "peakEquity": CAPITAL,
    }


def _mk_bot(idx: int) -> Dict:
    s = STRATEGIES[idx]
    return {
        "id": idx,
        "stratKey": s["key"],
        "strat": {
            "name": s["name"],
            "tag": s["tag"],
            "color": s["color"],
            "desc": s["desc"],
            "isPhantom": s["isPhantom"],
        },
        "engines": {tf["key"]: _mk_engine(tf["key"]) for tf in TIMEFRAMES},
    }


# ── Tick engine (mirrors tickEngine() from the JS) ───────────────────────────

def _tick_engine(eng: Dict, strat: Dict, price: float, ts_ms: int) -> None:
    tf_ms = TF_BY_KEY[eng["tfKey"]]["secs"] * 1000
    candle_time = (ts_ms // tf_ms) * tf_ms

    cc = eng["currentCandle"]
    if cc is None or cc["time"] != candle_time:
        if cc is not None:
            eng["candles"] = (eng["candles"] + [cc])[-100:]
        cc = {"time": candle_time, "open": price, "high": price, "low": price, "close": price, "volume": 0}
    cc = {
        **cc,
        "high":   max(cc["high"], price),
        "low":    min(cc["low"], price),
        "close":  price,
        "volume": cc["volume"] + 50 + random.random() * 150,
    }
    eng["currentCandle"] = cc

    eval_candles = eng["candles"] + [cc]
    res = strat["signal"](eval_candles)
    sig = res.get("signal", 0)
    eng["lastSignal"] = sig
    eng["lastMeta"] = res

    # ── Exit ─────────────────────────────────────────────────────────────────
    if eng["position"]:
        pos = eng["position"]
        new_hw = max(pos["highWater"], price)
        sl = pos["stopLoss"]

        if strat["isPhantom"] and (price - pos["entry"]) / pos["entry"] > 0.02:
            atr = calc_atr(eval_candles) or pos["entry"] * 0.02
            sl = max(pos["stopLoss"], new_hw - atr * max(0.5, 1.5 - ((price - pos["entry"]) / pos["entry"]) * 5))

        eng["position"] = {**pos, "highWater": new_hw, "stopLoss": sl}

        ep = reason = None
        if price <= sl:
            ep = price
            reason = "Trail Lock 🔒" if (price - pos["entry"]) / pos["entry"] > 0.01 else "Stop Loss 🔴"
        elif price >= pos["takeProfit"]:
            ep = price
            reason = "Take Profit 🟢"
        elif sig == -1:
            ep = price
            reason = "Signal Exit ⚡"

        if ep is not None:
            pnl = (ep - pos["entry"]) * pos["size"]
            eng["cash"] += ep * pos["size"]
            eng["wins"]   += 1 if pnl > 0 else 0
            eng["losses"] += 1 if pnl <= 0 else 0
            trade = {
                "entry":  round(pos["entry"], 3),
                "exit":   round(ep, 3),
                "size":   round(pos["size"], 4),
                "pnl":    round(pnl, 2),
                "pnlPct": round((ep - pos["entry"]) / pos["entry"] * 100, 2),
                "reason": reason,
                "time":   datetime.fromtimestamp(ts_ms / 1000).strftime("%I:%M:%S %p"),
                "regime": res.get("regime", "—"),
            }
            eng["trades"] = (eng["trades"] + [trade])[-50:]
            eng["position"] = None
            eng["status"] = "watching"

    # ── Entry ────────────────────────────────────────────────────────────────
    if eng["position"] is None and sig == 1 and eng["cash"] > 0:
        atr = calc_atr(eval_candles) or price * 0.02
        if strat["isPhantom"]:
            vol_s = max(0.5, min(2.0, 0.015 / max(atr / price, 0.001)))
            stop_d = atr * 1.5
            size = (eng["cash"] * 0.02 * vol_s) / stop_d
            sl = price - stop_d
            tp = price + stop_d * 2.5
        else:
            sl = price * 0.97
            tp = price * 1.05
            size = (eng["cash"] * 0.02) / (price - sl)
        cost = size * price
        if 0 < cost <= eng["cash"] * 0.95:
            eng["cash"] -= cost
            eng["position"] = {
                "entry":      price,
                "size":       size,
                "stopLoss":   sl,
                "takeProfit": tp,
                "highWater":  price,
            }
            eng["status"] = "in trade 🟡"

    # ── Equity ───────────────────────────────────────────────────────────────
    eq = eng["cash"] + (eng["position"]["size"] * price if eng["position"] else 0.0)
    eng["peakEquity"]  = max(eng["peakEquity"], eq)
    eng["maxDrawdown"] = max(eng["maxDrawdown"], (eng["peakEquity"] - eq) / eng["peakEquity"] * 100)
    eng["totalReturn"] = round((eq - CAPITAL) / CAPITAL * 100, 2)
    eng["winRate"]     = round(eng["wins"] / len(eng["trades"]) * 100, 1) if eng["trades"] else 0.0
    eng["equity"]      = (eng["equity"] + [{"t": ts_ms, "v": round(eq, 2)}])[-100:]
    if len(eval_candles) >= 50 and eng["status"] == "warming up":
        eng["status"] = "watching"


# ── Engine ───────────────────────────────────────────────────────────────────

class TradingEngine:
    def __init__(self) -> None:
        self.bots: List[Dict] = [_mk_bot(i) for i in range(3)]
        self.price:       float = 0.0
        self.price_change: float = 0.0
        self.price_hist:  List[Dict] = []
        self.connected:   bool = False
        self.running:     bool = False
        self.status:      str = "idle"
        self.last_upd:    Optional[str] = None
        self._lock = asyncio.Lock()
        self._last_tick:  float = 0.0

    # ── Public API ───────────────────────────────────────────────────────────

    def get_state(self) -> Dict:
        return {
            "bots":        self.bots,
            "price":       self.price,
            "priceChange": self.price_change,
            "priceHist":   self.price_hist[-150:],
            "connected":   self.connected,
            "running":     self.running,
            "status":      self.status,
            "lastUpd":     self.last_upd,
        }

    def set_running(self, value: bool) -> None:
        self.running = value
        self.status = "connecting" if value else "idle"

    def reset_bot(self, idx: int) -> None:
        if 0 <= idx < len(self.bots):
            self.bots[idx] = _mk_bot(idx)

    # ── Tick handler ─────────────────────────────────────────────────────────

    async def _handle_tick(self, price: float, change: float = 0.0) -> None:
        now = time.time()
        if now - self._last_tick < 1.0:
            return
        self._last_tick = now
        self.price = price
        self.price_change = change
        self.last_upd = datetime.now().strftime("%I:%M:%S %p")
        if self.status != "sim":
            self.status = "live"
        ts_ms = int(now * 1000)
        self.price_hist = (self.price_hist + [{"t": ts_ms, "p": price}])[-150:]

        async with self._lock:
            for bot_idx, bot in enumerate(self.bots):
                strat = STRATEGIES[bot_idx]
                for tf in TIMEFRAMES:
                    _tick_engine(bot["engines"][tf["key"]], strat, price, ts_ms)

    # ── Historical data ──────────────────────────────────────────────────────

    async def _fetch_historical(self) -> None:
        try:
            async with aiohttp.ClientSession() as session:
                for tf in TIMEFRAMES:
                    url = f"{KRAKEN_OHLC}?pair=SOLUSD&interval={TF_INTERVAL[tf['key']]}"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        raw = (data.get("result") or {}).get("SOLUSD", [])
                        candles = [
                            {
                                "time":   r[0] * 1000,
                                "open":   float(r[1]),
                                "high":   float(r[2]),
                                "low":    float(r[3]),
                                "close":  float(r[4]),
                                "volume": float(r[6]),
                            }
                            for r in raw[:-1]  # drop incomplete last candle
                        ][-100:]
                        async with self._lock:
                            for bot in self.bots:
                                e = bot["engines"][tf["key"]]
                                e["candles"] = candles
                                if len(candles) >= 50:
                                    e["status"] = "watching"
        except Exception as exc:
            print(f"[engine] Historical fetch failed: {exc}")

    # ── Kraken WebSocket ─────────────────────────────────────────────────────

    async def _kraken_loop(self) -> None:
        while True:
            try:
                async with websockets.connect(KRAKEN_WS, ping_interval=20, ping_timeout=10) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "ticker", "symbol": ["SOL/USD"]},
                    }))
                    self.connected = True
                    print("[engine] Kraken connected")
                    async for raw in ws:
                        if not self.running:
                            continue
                        msg = json.loads(raw)
                        if msg.get("channel") == "ticker" and msg.get("data"):
                            for d in msg["data"]:
                                if d.get("symbol") == "SOL/USD" and d.get("last"):
                                    await self._handle_tick(
                                        float(d["last"]),
                                        float(d.get("change_pct", 0.0)),
                                    )
            except Exception as exc:
                self.connected = False
                print(f"[engine] Kraken error: {exc} — reconnecting in 5s")
                await asyncio.sleep(5)

    # ── Simulation fallback ──────────────────────────────────────────────────

    async def _sim_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            if self.running and not self.connected:
                self.status = "sim"
                await self._handle_tick(next_sim(), 0.0)

    # ── Startup ──────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self.running = True
        self.status = "connecting"
        await self._fetch_historical()
        asyncio.create_task(self._kraken_loop())
        asyncio.create_task(self._sim_loop())
        print("[engine] Started — 3 bots × 4 timeframes")


engine = TradingEngine()
