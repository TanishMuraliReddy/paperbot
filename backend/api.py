"""
FastAPI application — exposes engine state and control endpoints.
The engine runs as a background asyncio task; this module just wires it up.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from engine import engine

app = FastAPI(title="PaperBot API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    await engine.start()


# ── Read ─────────────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    return engine.get_state()


# ── Control ──────────────────────────────────────────────────────────────────

@app.post("/api/start")
async def start_engine():
    engine.set_running(True)
    return {"ok": True}


@app.post("/api/stop")
async def stop_engine():
    engine.set_running(False)
    return {"ok": True}


@app.post("/api/bots/{bot_id}/reset")
async def reset_bot(bot_id: int):
    if bot_id < 0 or bot_id >= 3:
        raise HTTPException(status_code=404, detail="Bot not found")
    engine.reset_bot(bot_id)
    return {"ok": True}


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "price": engine.price, "connected": engine.connected}
