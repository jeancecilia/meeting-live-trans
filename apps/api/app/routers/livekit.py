"""LiveKit token generation routes (MTG-022).

Generates short-lived LiveKit participant tokens with embedded
application metadata. Permissions are validated server-side and
never trusted from browser input.
"""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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


class LiveKitTokenRequest(BaseModel):
    meeting_id: uuid.UUID
    participant_identity: str
    display_name: str


class LiveKitTokenResponse(BaseModel):
    token: str
    ws_url: str
    participant_identity: str


class GuestTokenRequest(BaseModel):
    meeting_id: uuid.UUID
    guest_identity: str
    display_name: str
    spoken_language: str = "en"


def _create_livekit_token(
    identity: str,
    display_name: str,
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
            room=metadata.get("meeting_id", ""),
            can_publish=True,
            can_subscribe=True,
        )
    )
    token.with_metadata("\n".join(f"{k}:{v}" for k, v in metadata.items() if v))
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
    caption_language = (
        "th" if user.preferred_spoken_language == "en" else "en"
    )

    metadata = {
        "app_role": user.role,
        "spoken_language": user.preferred_spoken_language,
        "caption_language": caption_language,
        "caption_access": "true",
        "meeting_id": str(meeting_id),
    }

    token = _create_livekit_token(identity, user.display_name, metadata)

    # Record participant
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
    """Generate a LiveKit token for a guest participant (no caption access)."""
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has ended")

    if body.spoken_language not in ("en", "th"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="spoken_language must be 'en' or 'th'",
        )

    identity = body.guest_identity
    metadata = {
        "app_role": "guest",
        "spoken_language": body.spoken_language,
        "caption_language": "",
        "caption_access": "false",
        "meeting_id": str(meeting_id),
    }

    token = _create_livekit_token(identity, body.display_name, metadata)

    participant = MeetingParticipant(
        meeting_id=meeting_id,
        user_id=None,
        guest_identity=identity,
        livekit_identity=identity,
        display_name=body.display_name,
        role="guest",
        spoken_language=body.spoken_language,
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
