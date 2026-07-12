from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.security import SecurityHeadersMiddleware
from app.routers import active_rooms, auth, captions, invites, livekit, meetings, webhooks

app = FastAPI(
    title="Meeting Live Trans API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
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
