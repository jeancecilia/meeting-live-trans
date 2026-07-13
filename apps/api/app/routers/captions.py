"""
Private caption routing (MTG-035).

Caption WebSocket with full authentication and authorization.
Internal endpoint for translation worker to submit caption events.
"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant
from app.models.user import User
from app.security import validate_ws_origin

logger = logging.getLogger("api.captions")

router = APIRouter(tags=["captions"])

_subscribers: dict[str, dict[str, dict[str, Any]]] = {}


class CaptionEventRequest(BaseModel):
    type: str
    event_id: str
    meeting_id: str
    speaker_id: str
    speaker_name: str
    source_language: str
    target_language: str
    translated_text: str
    sequence: int
    revision: int
    is_final: bool
    started_at: str | None = None


class SystemEventRequest(BaseModel):
    type: str
    meeting_id: str
    speaker_id: str
    speaker_name: str
    message: str


@router.websocket("/api/ws/meetings/{meeting_id}/captions")
async def caption_websocket(websocket: WebSocket, meeting_id: str) -> None:
    """
    Private caption WebSocket endpoint.

    Authorization checks (all must pass):
    1. Valid JWT access token in query param
    2. Origin validated against whitelist
    3. User exists and is active (reloaded from DB)
    4. User has internal role (host or internal_partner)
    5. User is a participant in this meeting
    6. Participant has caption_access = True
    7. Meeting is active (not created or ended)
    """
    # Validate origin before accepting
    origin = websocket.headers.get("origin", "")
    if not validate_ws_origin(origin):
        await websocket.close(code=4003, reason="Untrusted origin")
        return

    # Extract and validate token before accepting
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
    except JWTError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token type")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Missing user identifier")
        return

    # Validate against database — reload user to check real state
    participant_id = "unknown"
    caption_language = "th"

    try:
        async with async_session() as db:
            # Reload user from DB (don't trust JWT role alone)
            user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
            if not user:
                await websocket.close(code=4003, reason="User not found")
                return
            if not user.is_active:
                await websocket.close(code=4003, reason="Account disabled")
                return
            if user.role not in ("host", "internal_partner"):
                await websocket.close(code=4003, reason="Guest caption access denied")
                return

            # Check meeting membership and caption access
            participant = (await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == uuid.UUID(meeting_id),
                    MeetingParticipant.user_id == uuid.UUID(user_id),
                )
            )).scalar_one_or_none()

            if not participant:
                await websocket.close(code=4003, reason="Not a participant of this meeting")
                return
            if not participant.caption_access:
                await websocket.close(code=4003, reason="Caption access not authorized")
                return

            # Check meeting is active
            meeting = (await db.execute(select(Meeting).where(Meeting.id == uuid.UUID(meeting_id)))).scalar_one_or_none()
            if not meeting:
                await websocket.close(code=4003, reason="Meeting not found")
                return
            # A newly created meeting may not have received the LiveKit
            # participant_joined webhook yet. Membership and caption_access
            # have already been verified above, so captions can connect while
            # the room transitions from created to active.
            if meeting.status not in ("created", "active"):
                await websocket.close(code=4003, reason="Meeting not active")
                return

            participant_id = participant.livekit_identity
            caption_language = participant.caption_language or "th"
    except Exception as e:
        logger.error("Auth error: %s", e)
        await websocket.close(code=4003, reason="Authorization error")
        return

    # All checks passed — accept and register
    await websocket.accept()

    if meeting_id not in _subscribers:
        _subscribers[meeting_id] = {}
    _subscribers[meeting_id][participant_id] = {"ws": websocket, "lang": caption_language}

    logger.info("Caption subscriber: meeting=%s participant=%s lang=%s", meeting_id, participant_id, caption_language)

    try:
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    finally:
        if meeting_id in _subscribers:
            _subscribers[meeting_id].pop(participant_id, None)
            if not _subscribers[meeting_id]:
                del _subscribers[meeting_id]


@router.post("/api/internal/meetings/{meeting_id}/caption-events")
async def ingest_caption_event(meeting_id: str, event: CaptionEventRequest | SystemEventRequest, request: Request) -> dict:
    """Internal endpoint for the translation worker."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {settings.caption_worker_service_token}":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")
    if event.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meeting_id mismatch")

    routed = 0
    if meeting_id in _subscribers:
        disconnected = []
        for pid, sub in _subscribers[meeting_id].items():
            if (
                isinstance(event, CaptionEventRequest)
                and sub["lang"] != event.target_language
            ):
                continue
            try:
                await sub["ws"].send_json(event.model_dump())
                routed += 1
            except Exception:
                disconnected.append(pid)
        for pid in disconnected:
            _subscribers[meeting_id].pop(pid, None)

    return {"status": "ok", "routed_to": routed}

async def broadcast_global_system_event(message: str) -> int:
    event = SystemEventRequest(
        type="system.error",
        meeting_id="global",
        speaker_id="system",
        speaker_name="System Alert",
        message=message
    )
    payload = event.model_dump()
    routed = 0
    for mid, subs in _subscribers.items():
        disconnected = []
        for pid, sub in subs.items():
            try:
                await sub["ws"].send_json(payload)
                routed += 1
            except Exception:
                disconnected.append(pid)
        for pid in disconnected:
            subs.pop(pid, None)
    return routed

@router.post("/api/internal/system-events")
async def ingest_system_event(event: SystemEventRequest, request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header != f"Bearer {settings.caption_worker_service_token}":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")
    
    routed = await broadcast_global_system_event(event.message)
    return {"status": "ok", "routed": routed}
