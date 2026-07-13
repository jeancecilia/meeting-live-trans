import asyncio
import logging
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import active_rooms, auth, captions, invites, livekit, meetings, webhooks
from app.routers.captions import broadcast_global_system_event


class _AccessTokenRedactionFilter(logging.Filter):
    """Keep WebSocket access tokens out of Uvicorn access-log paths."""

    _token_query = re.compile(r"([?&]token=)[^&\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._token_query.sub(r"\1<redacted>", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._token_query.sub(r"\1<redacted>", value)
                if isinstance(value, str)
                else value
                for value in record.args
            )
        return True


for _logger_name in ("uvicorn.access", "uvicorn.error"):
    logging.getLogger(_logger_name).addFilter(_AccessTokenRedactionFilter())

async def health_monitor_task():
    while True:
        try:
            db_res = await health_database()
            if db_res["status"] == "error":
                await broadcast_global_system_event(f"Infrastructure Error: Database unreachable ({db_res.get('database')})")

            redis_res = await health_redis()
            if redis_res["status"] == "error":
                await broadcast_global_system_event(f"Infrastructure Error: Redis unreachable ({redis_res.get('redis')})")
                
            lk_res = await health_livekit()
            if lk_res["status"] == "error" or lk_res.get("livekit") == "degraded":
                await broadcast_global_system_event("Infrastructure Error: LiveKit unreachable or degraded")
                
        except Exception:
            pass
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(health_monitor_task())
    yield
    task.cancel()

app = FastAPI(
    title="Meeting Live Trans API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Register routers ──
app.include_router(active_rooms.router)
app.include_router(auth.router)
app.include_router(meetings.router)
app.include_router(invites.router)
app.include_router(livekit.router)
app.include_router(webhooks.router)
app.include_router(captions.router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "api"}


@app.get("/api/health/database")
async def health_database():
    from sqlalchemy import text
    from app.database import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}


@app.get("/api/health/redis")
async def health_redis():
    import redis.asyncio as redis_asyncio

    try:
        r = redis_asyncio.from_url(settings.redis_url)
        await r.ping()
        await r.close()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        return {"status": "error", "redis": str(e)}


@app.get("/api/health/livekit")
async def health_livekit():
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"http://{settings.livekit_host}:{settings.livekit_port}/"
            )
        return {"status": "ok", "livekit": "reachable" if resp.status_code < 500 else "degraded"}
    except Exception as e:
        return {"status": "error", "livekit": str(e)}
