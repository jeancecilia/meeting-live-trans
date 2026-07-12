"""
LiveKit webhook processing (MTG-025).

Handles participant join/leave, track publish/unpublish, and room
finished events. Signature verification is mandatory.
Duplicate delivery is idempotent.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

# Track processed event IDs (use Redis in production)
_processed_events: set[str] = set()


def _verify_webhook_signature(body: bytes, auth_header: str) -> bool:
    """
    Verify the LiveKit webhook signature.

    LiveKit signs webhooks with a SHA-256 HMAC using the API secret.
    The Authorization header is: "Bearer <base64-encoded-hash>"
    """
    try:
        token = auth_header.removeprefix("Bearer ").strip()
        expected = hmac.new(
            settings.livekit_api_secret.encode(),
            body,
            hashlib.sha256,
        ).digest()
        import base64

        decoded = base64.b64decode(token)
        return hmac.compare_digest(decoded, expected)
    except Exception:
        return False


@router.post("/livekit")
async def livekit_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Receive and process LiveKit webhook events with mandatory signature verification."""
    body = await request.body()
    auth_header = request.headers.get("Authorization", "")

    # Mandatory signature verification
    if not _verify_webhook_signature(body, auth_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    event = payload.get("event", "")
    event_id = payload.get("id", "")

    # Idempotency check
    if event_id and event_id in _processed_events:
        return {"status": "duplicate_ignored", "event_id": event_id}

    room_name = payload.get("room", {}).get("name", "")
    participant_data = payload.get("participant", {})
    participant_identity = participant_data.get("identity", "")

    # Find meeting by room_name (the LiveKit room uses room_name, not meeting_id)
    result = await db.execute(
        select(Meeting).where(Meeting.room_name == room_name)
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        return {"status": "meeting_not_found", "room_name": room_name}

    if event == "participant_joined":
        await _handle_participant_joined(db, meeting.id, participant_identity, event_id)
    elif event == "participant_left":
        await _handle_participant_left(db, meeting.id, participant_identity, event_id)
    elif event == "track_published":
        await _handle_track_published(db, meeting.id, participant_identity, payload, event_id)
    elif event == "track_unpublished":
        await _handle_track_unpublished(db, meeting.id, participant_identity, payload, event_id)
    elif event == "room_finished":
        await _handle_room_finished(db, meeting.id, event_id)

    if event_id:
        _processed_events.add(event_id)

    return {"status": "processed", "event": event}


async def _handle_participant_joined(
    db: AsyncSession, meeting_id: uuid.UUID, identity: str, event_id: str
) -> None:
    await db.execute(
        update(MeetingParticipant)
        .where(MeetingParticipant.livekit_identity == identity)
        .values(joined_at=datetime.now(timezone.utc))
    )
    await db.execute(
        update(Meeting)
        .where(Meeting.id == meeting_id, Meeting.status == "created")
        .values(status="active", started_at=datetime.now(timezone.utc))
    )
    db.add(AuditLog(
        meeting_id=meeting_id,
        event_type="participant_joined",
        metadata_json={"identity": identity, "webhook_event_id": event_id},
    ))
    await db.commit()


async def _handle_participant_left(
    db: AsyncSession, meeting_id: uuid.UUID, identity: str, event_id: str
) -> None:
    await db.execute(
        update(MeetingParticipant)
        .where(MeetingParticipant.livekit_identity == identity)
        .values(left_at=datetime.now(timezone.utc))
    )
    db.add(AuditLog(
        meeting_id=meeting_id,
        event_type="participant_left",
        metadata_json={"identity": identity, "webhook_event_id": event_id},
    ))
    await db.commit()


async def _handle_track_published(
    db: AsyncSession, meeting_id: uuid.UUID, identity: str, payload: dict, event_id: str
) -> None:
    track = payload.get("track", {})
    db.add(AuditLog(
        meeting_id=meeting_id,
        event_type="track_published",
        metadata_json={
            "identity": identity,
            "track_sid": track.get("sid"),
            "kind": track.get("kind"),
            "source": track.get("source"),
            "webhook_event_id": event_id,
        },
    ))
    await db.commit()


async def _handle_track_unpublished(
    db: AsyncSession, meeting_id: uuid.UUID, identity: str, payload: dict, event_id: str
) -> None:
    track = payload.get("track", {})
    db.add(AuditLog(
        meeting_id=meeting_id,
        event_type="track_unpublished",
        metadata_json={
            "identity": identity,
            "track_sid": track.get("sid"),
            "kind": track.get("kind"),
            "webhook_event_id": event_id,
        },
    ))
    await db.commit()


async def _handle_room_finished(
    db: AsyncSession, meeting_id: uuid.UUID, event_id: str
) -> None:
    await db.execute(
        update(Meeting)
        .where(Meeting.id == meeting_id)
        .values(status="ended", ended_at=datetime.now(timezone.utc))
    )
    db.add(AuditLog(
        meeting_id=meeting_id,
        event_type="room_finished",
        metadata_json={"webhook_event_id": event_id},
    ))
    await db.commit()
