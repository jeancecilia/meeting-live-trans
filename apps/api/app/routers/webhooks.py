"""
LiveKit webhook processing (MTG-025).

Handles participant/room events with mandatory signature verification
using LiveKit's WebhookReceiver.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from livekit import api as lk_api
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_processed_events: set[str] = set()


@router.post("/livekit")
async def livekit_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Receive and verify LiveKit webhook events."""
    body = await request.body()
    auth_header = request.headers.get("Authorization", "")

    # Verify using LiveKit's official WebhookReceiver
    try:
        receiver = lk_api.WebhookReceiver(
            settings.livekit_api_key,
            settings.livekit_api_secret,
        )
        event_data = receiver.receive(body, auth_header)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

    event = event_data.event if hasattr(event_data, "event") else event_data.get("event", "")
    event_id = getattr(event_data, "id", "") or event_data.get("id", "")

    if event_id and event_id in _processed_events:
        return {"status": "duplicate_ignored", "event_id": event_id}

    room_name = getattr(event_data, "room", {}).get("name", "") if hasattr(event_data, "room") else event_data.get("room", {}).get("name", "")
    participant = getattr(event_data, "participant", None) or event_data.get("participant", {})
    participant_identity = getattr(participant, "identity", "") if hasattr(participant, "identity") else participant.get("identity", "")

    result = await db.execute(select(Meeting).where(Meeting.room_name == room_name))
    meeting = result.scalar_one_or_none()
    if not meeting:
        return {"status": "meeting_not_found", "room_name": room_name}

    if event == "participant_joined":
        await _handle_participant_joined(db, meeting.id, participant_identity, event_id)
    elif event == "participant_left":
        await _handle_participant_left(db, meeting.id, participant_identity, event_id)
    elif event == "track_published":
        track = getattr(event_data, "track", {}) if hasattr(event_data, "track") else event_data.get("track", {})
        await _handle_track_event(db, meeting.id, participant_identity, track, "track_published", event_id)
    elif event == "track_unpublished":
        track = getattr(event_data, "track", {}) if hasattr(event_data, "track") else event_data.get("track", {})
        await _handle_track_event(db, meeting.id, participant_identity, track, "track_unpublished", event_id)
    elif event == "room_finished":
        await _handle_room_finished(db, meeting.id, event_id)

    if event_id:
        _processed_events.add(event_id)

    return {"status": "processed", "event": event}


async def _handle_participant_joined(db: AsyncSession, meeting_id: uuid.UUID, identity: str, event_id: str) -> None:
    await db.execute(
        update(MeetingParticipant)
        .where(MeetingParticipant.livekit_identity == identity)
        .values(joined_at=datetime.now(timezone.utc))
    )
    await db.execute(update(Meeting).where(Meeting.id == meeting_id, Meeting.status == "created").values(status="active", started_at=datetime.now(timezone.utc)))
    db.add(AuditLog(meeting_id=meeting_id, event_type="participant_joined", metadata_json={"identity": identity, "webhook_event_id": event_id}))
    await db.commit()


async def _handle_participant_left(db: AsyncSession, meeting_id: uuid.UUID, identity: str, event_id: str) -> None:
    await db.execute(update(MeetingParticipant).where(MeetingParticipant.livekit_identity == identity).values(left_at=datetime.now(timezone.utc)))
    db.add(AuditLog(meeting_id=meeting_id, event_type="participant_left", metadata_json={"identity": identity, "webhook_event_id": event_id}))
    await db.commit()


async def _handle_track_event(db: AsyncSession, meeting_id: uuid.UUID, identity: str, track: dict, event_type: str, event_id: str) -> None:
    db.add(AuditLog(meeting_id=meeting_id, event_type=event_type, metadata_json={
        "identity": identity,
        "track_sid": track.get("sid") if isinstance(track, dict) else getattr(track, "sid", ""),
        "kind": track.get("kind") if isinstance(track, dict) else getattr(track, "kind", ""),
        "source": track.get("source") if isinstance(track, dict) else getattr(track, "source", ""),
        "webhook_event_id": event_id,
    }))
    await db.commit()


async def _handle_room_finished(db: AsyncSession, meeting_id: uuid.UUID, event_id: str) -> None:
    await db.execute(update(Meeting).where(Meeting.id == meeting_id).values(status="ended", ended_at=datetime.now(timezone.utc)))
    db.add(AuditLog(meeting_id=meeting_id, event_type="room_finished", metadata_json={"webhook_event_id": event_id}))
    await db.commit()
