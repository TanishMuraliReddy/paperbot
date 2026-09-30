# PaperBot v3

SOL/USD paper trading simulator — 3 strategies, 4 timeframes each, 12 independent engines running simultaneously.

The trading engine runs as a standalone Python backend (FastAPI + Kraken WebSocket). The React UI is a read-only dashboard that polls the engine every second. Closing the browser has no effect on trading.

---

## Requirements

### Downloads

| Software | Version | Download |
|----------|---------|----------|
| Python | 3.11 or newer | https://www.python.org/downloads/ |
| Node.js | 18 or newer | https://nodejs.org/ |
| Git (optional) | any | https://git-scm.com/ |

> **Windows install tip:** When installing Python, check **"Add Python to PATH"** on the first screen of the installer.

### Python packages (auto-installed in setup below)
- `fastapi` — API server
- `uvicorn[standard]` — ASGI server
- `websockets` — Kraken WebSocket connection
- `aiohttp` — fetching historical candle data

### Node packages (auto-installed in setup below)
- `react` 19 — UI framework
- `recharts` 3 — charts

---

## Setup (first time only)

### 1. Install Python dependencies

Open a terminal in the project root:

```
cd V3_Paperbot\backend
py -m pip install -r requirements.txt
```

### 2. Install Node dependencies

```
cd V3_Paperbot\paperbot
npm install
```

---

## Running (every time)

You need **two terminals open at the same time** — one for the engine, one for the UI.

### Terminal 1 — Start the engine

```
cd V3_Paperbot\backend
py -m uvicorn api:app --reload --port 8000
```

Wait until you see:
```
[engine] Started — 3 bots × 4 timeframes
INFO:     Uvicorn running on http://0.0.0.0:8000
[engine] Kraken connected
```

### Terminal 2 — Start the UI

```
cd V3_Paperbot\paperbot
npm start
```

This opens `http://localhost:3000` automatically.

### Shortcut (Windows only)

Double-click `start_dev.bat` in the project root — it opens both terminals automatically.

---

## Using the app

1. The dashboard loads and shows "Connecting..." briefly, then populates with live data
2. Click **▶ START** in the top-right to begin trading
3. The status dot blinks green — `LIVE` means Kraken data, `SIM` means fallback simulation
4. Select a bot from the left panel to view its strategy
5. Select a timeframe tab (1 MIN / 5 MIN / 15 MIN / 1 HOUR) to drill into that engine
6. Use the **Chart / Equity / Trades / Phantom Intel** tabs to explore

---

## Project structure

```
V3_Paperbot/
├── backend/
│   ├── api.py          — FastAPI server, endpoints
│   ├── engine.py       — Trading engine, Kraken WS, tick processing
│   ├── indicators.py   — EMA, RSI, ATR, MACD, BB, UTBot, ADX, OFI, Regime, Momentum
│   ├── strategies.py   — UT+MACD+RSI · MACD+BB · PHANTOM
│   └── requirements.txt
├── paperbot/
│   └── src/
│       └── live_paper_trading_v2.jsx  — entire UI (polls /api/state, no engine logic)
├── Dockerfile          — Python engine image
├── docker-compose.yml  — engine + UI, restart: unless-stopped
└── start_dev.bat       — Windows shortcut to start both processes
```

---

## Strategies

| Strategy | Tag | Logic |
|----------|-----|-------|
| UT Bot + MACD + RSI | MOMENTUM | ATR trailing stop flip + MACD crossover + RSI filter |
| MACD + Bollinger | CROSSOVER | MACD crossover confirmed by price position vs BB mid |
| PHANTOM | REGIME·AI | Classifies market regime (trending/ranging/volatile), uses order flow index + composite momentum score for adaptive entries and a trailing stop that tightens as profit grows |

Each strategy runs independently on all 4 timeframes. Starting capital: $10,000 per engine.

---

## API endpoints

The engine exposes a REST API at `http://localhost:8000`:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/state` | Full bot state — bots, price, equity, trades |
| POST | `/api/start` | Resume tick processing |
| POST | `/api/stop` | Pause tick processing |
| POST | `/api/bots/{id}/reset` | Reset one bot (0, 1, or 2) |
| GET | `/health` | Quick health check |

---

## Docker (production / always-on)

Runs both the engine and UI in containers. The engine restarts automatically on crash or reboot.

```
cd V3_Paperbot
docker-compose up -d
```

- UI → `http://localhost:3000`
- Engine API → `http://localhost:8000`

To stop:
```
docker-compose down
```

---

## Troubleshooting

**UI shows "Cannot reach engine"**
The Python engine is not running. Start it with `py -m uvicorn api:app --port 8000` from the `backend/` folder.

**`py` is not recognized**
Use `python` instead — or install Python and make sure it's added to PATH.

**`npm start` fails**
Run `npm install` first from the `paperbot/` folder.

**Status shows SIM instead of LIVE**
The engine could not connect to Kraken (network/firewall). It falls back to a simulated price feed automatically. Trading still works normally.

**Port 8000 already in use**
Change the port: `py -m uvicorn api:app --port 8001` and set `REACT_APP_API_URL=http://localhost:8001` before running `npm start`.
