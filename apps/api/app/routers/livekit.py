"""LiveKit token routes — uses preferred_caption_language from user profile."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_internal_role
from app.config import settings
from app.database import get_db
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant
from app.models.user import User

router = APIRouter(tags=["livekit"])


def _get_lk_api():
    from livekit import api
    return api


class LiveKitTokenResponse(BaseModel):
    token: str
    ws_url: str
    participant_identity: str


class GuestTokenRequest(BaseModel):
    guest_session_token: str
    display_name: str


def _create_guest_session_token(meeting_id: str, guest_identity: str, spoken_language: str, invite_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    payload = {
        "sub": guest_identity, "meeting_id": meeting_id, "spoken_language": spoken_language,
        "invite_id": invite_id, "role": "guest", "type": "guest_session",
        "exp": expire, "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def _decode_guest_session(token: str) -> dict:
    try:
        p = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if p.get("type") != "guest_session":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
        return p
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid guest session")


def _create_livekit_token(identity: str, display_name: str, room_name: str, metadata: dict) -> str:
    api = _get_lk_api()
    t = api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
    t.with_identity(identity).with_name(display_name)
    t.with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True))
    t.with_metadata("; ".join(f"{k}:{v}" for k, v in metadata.items() if v))
    t.with_ttl(timedelta(minutes=30))
    return t.to_jwt()


@router.post("/api/meetings/{meeting_id}/livekit-token", response_model=LiveKitTokenResponse)
async def get_internal_token(
    meeting_id: uuid.UUID,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    meeting = (await db.execute(select(Meeting).where(Meeting.id == meeting_id))).scalar_one_or_none()
    if not meeting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Meeting has ended")

    identity = f"internal_{user.id.hex[:12]}"
    caption_language = user.preferred_caption_language  # User's own caption preference

    metadata = {
        "app_role": user.role,
        "spoken_language": user.preferred_spoken_language,
        "caption_language": caption_language,
        "caption_access": "true",
    }

    token_str = _create_livekit_token(identity, user.display_name, meeting.room_name, metadata)

    # Upsert participant
    existing = (await db.execute(select(MeetingParticipant).where(
        MeetingParticipant.meeting_id == meeting_id,
        MeetingParticipant.livekit_identity == identity,
    ))).scalar_one_or_none()

    if existing:
        existing.joined_at = datetime.now(timezone.utc)
        existing.left_at = None
        existing.caption_language = caption_language
    else:
        db.add(MeetingParticipant(
            meeting_id=meeting_id, user_id=user.id, livekit_identity=identity,
            display_name=user.display_name, role=user.role,
            spoken_language=user.preferred_spoken_language,
            caption_language=caption_language, caption_access=True,
        ))
    await db.commit()

    return LiveKitTokenResponse(
        token=token_str,
        ws_url=settings.livekit_public_ws_url,
        participant_identity=identity,
    )


@router.post("/api/meetings/{meeting_id}/livekit-token/guest", response_model=LiveKitTokenResponse)
async def get_guest_token(
    meeting_id: uuid.UUID,
    body: GuestTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    session = _decode_guest_session(body.guest_session_token)
    if session["meeting_id"] != str(meeting_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session not valid for this meeting")

    meeting = (await db.execute(select(Meeting).where(Meeting.id == meeting_id))).scalar_one_or_none()
    if not meeting:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Meeting has ended")

    identity = session["sub"]
    spoken_language = session.get("spoken_language", "en")

    metadata = {"app_role": "guest", "spoken_language": spoken_language, "caption_access": "false"}

    token_str = _create_livekit_token(identity, body.display_name, meeting.room_name, metadata)

    existing = (await db.execute(select(MeetingParticipant).where(
        MeetingParticipant.meeting_id == meeting_id,
        MeetingParticipant.livekit_identity == identity,
    ))).scalar_one_or_none()

    if existing:
        existing.joined_at = datetime.now(timezone.utc)
        existing.left_at = None
    else:
        db.add(MeetingParticipant(
            meeting_id=meeting_id, user_id=None, guest_identity=identity,
            livekit_identity=identity, display_name=body.display_name,
            role="guest", spoken_language=spoken_language,
            caption_language=None, caption_access=False,
        ))
    await db.commit()

    return LiveKitTokenResponse(
        token=token_str,
        ws_url=settings.livekit_public_ws_url,
        participant_identity=identity,
    )
