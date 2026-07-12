"""
Private caption routing (MTG-035).

Caption WebSocket endpoint with real authentication and authorization.
Internal endpoint for the translation worker to submit caption events.
Guest connections always receive HTTP 403.
"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant

logger = logging.getLogger("api.captions")

router = APIRouter(tags=["captions"])

# Connected caption subscribers: meeting_id → {participant_id → {"ws": WebSocket, "lang": str}}
_subscribers: dict[str, dict[str, dict[str, Any]]] = {}


# ──── Caption event schema ────

class CaptionEventRequest(BaseModel):
    type: str  # "caption.delta" or "caption.final"
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


# ──── WebSocket endpoint ────

@router.websocket("/api/ws/meetings/{meeting_id}/captions")
async def caption_websocket(
    websocket: WebSocket,
    meeting_id: str,
) -> None:
    """
    Private caption WebSocket endpoint.

    Authorization checks:
    1. Valid JWT token in query param
    2. Token belongs to an internal user (host or internal_partner)
    3. User is a participant in this meeting
    4. Participant has caption_access = True
    5. Meeting is active
    """
    await websocket.accept()

    participant_id = "unknown"
    caption_language = "th"

    try:
        # 1. Validate JWT token
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

        # 2. Check internal role
        role = payload.get("role", "")
        if role not in ("host", "internal_partner"):
            await websocket.close(code=4003, reason="Guest caption access denied")
            return

        # 3. Check participant record
        async with async_session() as db:
            result = await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == uuid.UUID(meeting_id),
                    MeetingParticipant.user_id == uuid.UUID(user_id),
                )
            )
            participant = result.scalar_one_or_none()

            if not participant:
                await websocket.close(code=4003, reason="Not a participant of this meeting")
                return

            # 4. Check caption_access
            if not participant.caption_access:
                await websocket.close(code=4003, reason="Caption access not authorized")
                return

            # 5. Check meeting is active
            meeting_result = await db.execute(
                select(Meeting).where(Meeting.id == uuid.UUID(meeting_id))
            )
            meeting = meeting_result.scalar_one_or_none()
            if not meeting or meeting.status == "ended":
                await websocket.close(code=4003, reason="Meeting not active")
                return

            participant_id = participant.livekit_identity
            caption_language = participant.caption_language or "th"

        # Register subscriber
        if meeting_id not in _subscribers:
            _subscribers[meeting_id] = {}

        _subscribers[meeting_id][participant_id] = {
            "ws": websocket,
            "lang": caption_language,
        }

        logger.info(
            "Caption subscriber connected: meeting=%s participant=%s lang=%s",
            meeting_id,
            participant_id,
            caption_language,
        )

        # Keep alive and handle pings
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
    except Exception as e:
        logger.error("Caption WebSocket error: %s", e)
    finally:
        if meeting_id in _subscribers:
            _subscribers[meeting_id].pop(participant_id, None)
            if not _subscribers[meeting_id]:
                del _subscribers[meeting_id]


# ──── Internal caption ingest endpoint ────

@router.post("/api/internal/meetings/{meeting_id}/caption-events")
async def ingest_caption_event(
    meeting_id: str,
    event: CaptionEventRequest,
    request: Request,
) -> dict:
    """
    Internal endpoint for the translation worker to submit caption events.

    Protected by service-to-service token via Authorization header.
    """
    # Validate service token
    auth_header = request.headers.get("Authorization", "")
    expected = f"Bearer {settings.app_secret_key}"
    if auth_header != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service token")

    # Validate meeting_id matches event
    if event.meeting_id != meeting_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="meeting_id mismatch")

    # Route to subscribers with language filtering
    routed_count = await _route_caption_event(meeting_id, event.model_dump())

    return {"status": "ok", "routed_to": routed_count}


# ──── Routing function ────

async def _route_caption_event(
    meeting_id: str,
    caption_event: dict,
) -> int:
    """
    Route a caption event only to subscribers whose caption language matches.

    - English speaker → Thai translation → Thai-caption subscribers only
    - Thai speaker → English translation → English-caption subscribers only
    - Subscribers with mismatched languages do not receive the event
    """
    if meeting_id not in _subscribers:
        return 0

    target_language = caption_event.get("target_language", "")
    routed = 0
    disconnected = []

    for pid, sub in _subscribers[meeting_id].items():
        # Only send if subscriber's caption language matches the translation target
        if sub["lang"] != target_language:
            continue

        try:
            await sub["ws"].send_json(caption_event)
            routed += 1
        except Exception:
            disconnected.append(pid)

    for pid in disconnected:
        _subscribers[meeting_id].pop(pid, None)

    return routed


# Import at bottom to avoid circular dependency
from app.database import async_session
