# PaperBot

SOL/USD paper trading simulator: 3 strategies × 4 timeframes, running as 12 independent engines.

- **backend/**: FastAPI + Kraken WebSocket trading engine (falls back to a GBM price simulation if Kraken is unavailable). Runs independently of the browser.
- **paperbot/**: React dashboard that polls the engine every second.

## Run

**Docker:** `docker compose up --build`, then open UI at http://localhost:3000 (API at http://localhost:8000).

**Local (Windows):** `start_dev.bat`

See [paperbot/README.md](paperbot/README.md) for more detail.
