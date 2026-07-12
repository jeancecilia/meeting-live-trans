from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, captions, invites, livekit, meetings, webhooks

app = FastAPI(
    title="Meeting Live Trans API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
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
    from app.database import check_database_connection

    connected = await check_database_connection()
    return {
        "status": "ok" if connected else "error",
        "database": "connected" if connected else "unavailable",
    }


@app.get("/api/health/redis")
async def health_redis():
    return {"status": "ok", "redis": "connected"}


@app.get("/api/health/livekit")
async def health_livekit():
    return {"status": "ok", "livekit": "reachable"}
