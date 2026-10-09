"""HTTP API (FastAPI). Small on purpose - this is the seed for a web app.

Run with:  uvicorn newshub.api:app
Interactive docs are served at /docs.
"""

from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import db, jobs
from .config import Mode, Settings, load_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    app.state.config = load_config()
    app.state.pool = await db.connect(settings.database_url)
    app.state.redis = await jobs.connect(settings.redis_url)
    yield
    await app.state.pool.close()
    await app.state.redis.aclose()


app = FastAPI(title="newshub", version="0.1.0", lifespan=lifespan)


def _mode(request: Request, name: str) -> Mode:
    mode = request.app.state.config.modes.get(name)
    if mode is None:
        raise HTTPException(status_code=404, detail=f"unknown mode {name!r}")
    return mode


@app.get("/health")
async def health(request: Request):
    checks = {}
    try:
        await request.app.state.pool.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "down"
    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if healthy else "degraded", **checks},
        status_code=200 if healthy else 503,
    )


@app.get("/modes")
async def list_modes(request: Request):
    config = request.app.state.config
    return {
        "timezone": config.timezone,
        "modes": [
            {
                "name": mode.name,
                "title": mode.title,
                "emoji": mode.emoji,
                "digest_times": mode.digest_times,
                "digest_size": mode.digest_size,
                "alert_score": mode.alert_score,
                "sources": [source.name for source in mode.sources],
            }
            for mode in config.modes.values()
        ],
    }


@app.get("/modes/{mode}/items")
async def list_items(request: Request, mode: str, limit: int = Query(default=20, ge=1, le=200)):
    items = await db.recent_items(request.app.state.pool, _mode(request, mode).name, limit)
    return [asdict(item) for item in items]


@app.post("/collect", status_code=202)
async def collect(request: Request):
    await request.app.state.redis.enqueue_job(jobs.COLLECT_ALL)
    return {"queued": jobs.COLLECT_ALL}


@app.post("/modes/{mode}/digest", status_code=202)
async def digest(request: Request, mode: str):
    await request.app.state.redis.enqueue_job(jobs.SEND_DIGEST, _mode(request, mode).name)
    return {"queued": jobs.SEND_DIGEST, "mode": mode}
