"""
Internal endpoint for the worker to discover active meeting rooms.

Protected by service token.
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.meeting import Meeting

router = APIRouter(tags=["internal"])


@router.get("/api/internal/active-rooms")
async def list_active_rooms(request: Request) -> list[dict]:
    """Return active meetings that need translation workers."""
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {settings.caption_worker_service_token}":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")

    async with async_session() as db:
        result = await db.execute(
            select(Meeting).where(Meeting.status == "active")
        )
        meetings = result.scalars().all()

    return [
        {"id": str(m.id), "room_name": m.room_name, "status": m.status}
        for m in meetings
    ]
