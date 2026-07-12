"""LiveKit token generation routes (MTG-022).

Generates short-lived LiveKit participant tokens with embedded
application metadata. Guest tokens require a signed guest-session JWT.
Permissions are validated server-side and never trusted from browser input.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError, jwt
from livekit import api as lk_api
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_internal_role
from app.config import settings
from app.database import get_db
from app.models.meeting import Meeting
from app.models.meeting_participant import MeetingParticipant
from app.models.user import User

router = APIRouter(tags=["livekit"])


class LiveKitTokenResponse(BaseModel):
    token: str
    ws_url: str
    participant_identity: str


class GuestTokenRequest(BaseModel):
    guest_session_token: str  # Signed JWT from join flow
    display_name: str


def _create_guest_session_token(
    meeting_id: str,
    guest_identity: str,
    spoken_language: str,
    invite_id: str,
    ttl_minutes: int = 30,
) -> str:
    """Create a signed guest-session JWT after invite validation."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = {
        "sub": guest_identity,
        "meeting_id": meeting_id,
        "spoken_language": spoken_language,
        "invite_id": invite_id,
        "role": "guest",
        "type": "guest_session",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def _decode_guest_session(token: str) -> dict:
    """Decode and validate a guest-session JWT."""
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
        if payload.get("type") != "guest_session":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired guest session")


def _create_livekit_token(
    identity: str,
    display_name: str,
    room_name: str,
    metadata: dict,
    ttl_minutes: int = 30,
) -> str:
    """Create a short-lived LiveKit access token."""
    token = lk_api.AccessToken(
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
    )
    token.with_identity(identity)
    token.with_name(display_name)
    token.with_grants(
        lk_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )
    )
    # Store metadata as string (LiveKit format)
    meta_str = "; ".join(f"{k}:{v}" for k, v in metadata.items() if v)
    token.with_metadata(meta_str)
    token.ttl = ttl_minutes * 60
    return token.to_jwt()


@router.post("/api/meetings/{meeting_id}/livekit-token", response_model=LiveKitTokenResponse)
async def get_internal_livekit_token(
    meeting_id: uuid.UUID,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LiveKitTokenResponse:
    """Generate a LiveKit token for an internal user."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has ended")

    identity = f"internal_{user.id.hex[:12]}"
    caption_language = "th" if user.preferred_spoken_language == "en" else "en"

    metadata = {
        "app_role": user.role,
        "spoken_language": user.preferred_spoken_language,
        "caption_language": caption_language,
        "caption_access": "true",
    }

    token = _create_livekit_token(
        identity=identity,
        display_name=user.display_name,
        room_name=meeting.room_name,
        metadata=metadata,
    )

    # Upsert participant (allows reconnection)
    existing = await db.execute(
        select(MeetingParticipant).where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.livekit_identity == identity,
        )
    )
    participant = existing.scalar_one_or_none()

    if participant:
        participant.joined_at = datetime.now(timezone.utc)
        participant.left_at = None
    else:
        participant = MeetingParticipant(
            meeting_id=meeting_id,
            user_id=user.id,
            livekit_identity=identity,
            display_name=user.display_name,
            role=user.role,
            spoken_language=user.preferred_spoken_language,
            caption_language=caption_language,
            caption_access=True,
        )
        db.add(participant)

    await db.commit()

    return LiveKitTokenResponse(
        token=token,
        ws_url=settings.livekit_ws_url,
        participant_identity=identity,
    )


@router.post("/api/meetings/{meeting_id}/livekit-token/guest", response_model=LiveKitTokenResponse)
async def get_guest_livekit_token(
    meeting_id: uuid.UUID,
    body: GuestTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LiveKitTokenResponse:
    """
    Generate a LiveKit token for a guest participant.

    Requires a signed guest-session JWT from the invitation join flow.
    The guest cannot supply their own meeting_id or identity.
    """
    session = _decode_guest_session(body.guest_session_token)

    # Validate session claims match request
    if session["meeting_id"] != str(meeting_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session not valid for this meeting")

    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has ended")

    identity = session["sub"]  # guest_identity from join flow
    spoken_language = session.get("spoken_language", "en")

    metadata = {
        "app_role": "guest",
        "spoken_language": spoken_language,
        "caption_access": "false",
    }

    token = _create_livekit_token(
        identity=identity,
        display_name=body.display_name,
        room_name=meeting.room_name,
        metadata=metadata,
    )

    # Upsert participant
    existing = await db.execute(
        select(MeetingParticipant).where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.livekit_identity == identity,
        )
    )
    participant = existing.scalar_one_or_none()

    if participant:
        participant.joined_at = datetime.now(timezone.utc)
        participant.left_at = None
    else:
        participant = MeetingParticipant(
            meeting_id=meeting_id,
            user_id=None,
            guest_identity=identity,
            livekit_identity=identity,
            display_name=body.display_name,
            role="guest",
            spoken_language=spoken_language,
            caption_language=None,
            caption_access=False,
        )
        db.add(participant)

    await db.commit()

    return LiveKitTokenResponse(
        token=token,
        ws_url=settings.livekit_ws_url,
        participant_identity=identity,
    )
