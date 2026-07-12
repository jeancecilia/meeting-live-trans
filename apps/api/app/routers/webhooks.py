"""LiveKit webhook processing with mandatory signature verification."""

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
_processed: set[str] = set()


@router.post("/livekit")
async def webhook(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    body = await request.body()
    auth = request.headers.get("Authorization", "")

    try:
        v = lk_api.TokenVerifier(settings.livekit_api_key, settings.livekit_api_secret)
        r = lk_api.WebhookReceiver(v)
        ev = r.receive(body.decode("utf-8"), auth)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")

    event = ev.event
    eid = ev.id
    if eid and eid in _processed:
        return {"status": "duplicate_ignored", "event_id": eid}

    room_name = ev.room.name if ev.HasField("room") else ""
    pid = ev.participant.identity if ev.HasField("participant") else ""

    meeting = (await db.execute(select(Meeting).where(Meeting.room_name == room_name))).scalar_one_or_none()
    if not meeting:
        return {"status": "meeting_not_found", "room_name": room_name}

    mid = meeting.id

    if event == "participant_joined":
        await db.execute(update(MeetingParticipant).where(
            MeetingParticipant.meeting_id == mid, MeetingParticipant.livekit_identity == pid
        ).values(joined_at=datetime.now(timezone.utc)))
        await db.execute(update(Meeting).where(Meeting.id == mid, Meeting.status == "created").values(status="active", started_at=datetime.now(timezone.utc)))
        db.add(AuditLog(meeting_id=mid, event_type="participant_joined", metadata_json={"identity": pid, "webhook_event_id": eid}))
    elif event == "participant_left":
        await db.execute(update(MeetingParticipant).where(
            MeetingParticipant.meeting_id == mid, MeetingParticipant.livekit_identity == pid
        ).values(left_at=datetime.now(timezone.utc)))
        db.add(AuditLog(meeting_id=mid, event_type="participant_left", metadata_json={"identity": pid, "webhook_event_id": eid}))
    elif event == "track_published":
        db.add(AuditLog(meeting_id=mid, event_type="track_published", metadata_json={"identity": pid, "track_sid": ev.track.sid if ev.HasField("track") else "", "webhook_event_id": eid}))
    elif event == "track_unpublished":
        db.add(AuditLog(meeting_id=mid, event_type="track_unpublished", metadata_json={"identity": pid, "track_sid": ev.track.sid if ev.HasField("track") else "", "webhook_event_id": eid}))
    elif event == "room_finished":
        await db.execute(update(Meeting).where(Meeting.id == mid).values(status="ended", ended_at=datetime.now(timezone.utc)))
        db.add(AuditLog(meeting_id=mid, event_type="room_finished", metadata_json={"webhook_event_id": eid}))

    await db.commit()
    if eid:
        _processed.add(eid)
    return {"status": "processed", "event": event}
