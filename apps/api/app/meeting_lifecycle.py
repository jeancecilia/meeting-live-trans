"""Authoritative one-hour meeting lifecycle management.

Meetings that have started run for at most ``meeting_max_duration_minutes``.
Unstarted rooms use their creation time as the deadline so abandoned links do
not remain joinable forever. Ending a room also asks LiveKit to disconnect all
participants; the database transition remains authoritative if LiveKit is
already empty or temporarily unreachable.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.audit_log import AuditLog
from app.models.meeting import Meeting

logger = logging.getLogger("meeting-lifecycle")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def meeting_deadline(meeting: Meeting) -> datetime | None:
    """Return the authoritative deadline for a non-ended meeting."""
    if meeting.status == "ended":
        return meeting.ended_at

    anchor = meeting.started_at or meeting.created_at
    if anchor is None:
        return None
    return _as_utc(anchor) + timedelta(minutes=settings.meeting_max_duration_minutes)


def meeting_is_expired(meeting: Meeting, now: datetime | None = None) -> bool:
    if meeting.status == "ended":
        return True
    deadline = meeting_deadline(meeting)
    if deadline is None:
        return False
    current = _as_utc(now or datetime.now(timezone.utc))
    return current >= deadline


def livekit_http_url() -> str:
    return (
        settings.livekit_ws_url.replace("wss://", "https://", 1)
        .replace("ws://", "http://", 1)
        .rstrip("/")
    )


async def disconnect_livekit_room(room_name: str) -> bool:
    """Disconnect a LiveKit room without exposing credentials in logs."""
    from livekit import api

    client = api.LiveKitAPI(
        url=livekit_http_url(),
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    try:
        await client.room.delete_room(api.DeleteRoomRequest(room=room_name))
        return True
    except Exception as exc:
        if getattr(exc, "status", None) == 404:
            # An abandoned meeting may never have instantiated a LiveKit room.
            return True
        # A created meeting may never have created a LiveKit room. The database
        # expiry is still correct, so report only the operational error type.
        logger.warning(
            "LiveKit room disconnect did not complete: room=%s error=%s",
            room_name,
            type(exc).__name__,
        )
        return False
    finally:
        await client.aclose()


async def expire_due_meetings_once(now: datetime | None = None) -> int:
    """End every due meeting and disconnect any corresponding LiveKit rooms."""
    current = _as_utc(now or datetime.now(timezone.utc))
    expired_rooms: list[str] = []

    async with async_session() as db:
        result = await db.execute(
            select(Meeting)
            .where(Meeting.status.in_(("created", "active")))
            .with_for_update(skip_locked=True)
        )
        for meeting in result.scalars().all():
            if not meeting_is_expired(meeting, current):
                continue
            meeting.status = "ended"
            meeting.ended_at = current
            expired_rooms.append(meeting.room_name)
            db.add(
                AuditLog(
                    meeting_id=meeting.id,
                    event_type="meeting_auto_ended",
                    metadata_json={
                        "reason": "maximum_duration_reached",
                        "duration_minutes": settings.meeting_max_duration_minutes,
                    },
                )
            )
        await db.commit()

    for room_name in expired_rooms:
        await disconnect_livekit_room(room_name)

    if expired_rooms:
        logger.info("Automatically ended meetings: count=%d", len(expired_rooms))
    return len(expired_rooms)


async def meeting_expiry_task() -> None:
    """Run the expiry sweep until the application shuts down."""
    while True:
        try:
            await expire_due_meetings_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Meeting expiry sweep failed: error=%s", type(exc).__name__)
        await asyncio.sleep(max(5, settings.meeting_expiry_sweep_seconds))
