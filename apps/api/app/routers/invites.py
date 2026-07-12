"""Guest invitation routes (MTG-021).

Invite tokens are stored as SHA-256 hashes. The raw token is returned
once at creation time and never stored in plaintext.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_internal_role
from app.database import get_db
from app.models.meeting import Meeting
from app.models.meeting_invite import MeetingInvite
from app.models.user import User

router = APIRouter(tags=["invites"])


class CreateInviteRequest(BaseModel):
    guest_name: str
    expected_spoken_language: str = "en"
    expires_in_hours: int = 24
    max_uses: int = 1


class InviteResponse(BaseModel):
    id: uuid.UUID
    token: str
    invite_url: str
    guest_name: str
    expires_at: str
    max_uses: int
    model_config = {"from_attributes": True}


class InvitePreviewResponse(BaseModel):
    guest_name: str
    meeting_title: str
    expected_spoken_language: str
    expires_at: str
    is_valid: bool


class JoinRequest(BaseModel):
    display_name: str


class JoinResponse(BaseModel):
    meeting_id: uuid.UUID
    guest_identity: str
    role: str = "guest"
    caption_access: bool = False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


# ──── Internal routes ────


@router.post(
    "/api/meetings/{meeting_id}/invites",
    response_model=InviteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    meeting_id: uuid.UUID,
    body: CreateInviteRequest,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteResponse:
    # Validate meeting exists and is not ended
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has ended")

    if body.expected_spoken_language not in ("en", "th"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_spoken_language must be 'en' or 'th'",
        )

    raw_token = _generate_invite_token()
    invite = MeetingInvite(
        meeting_id=meeting_id,
        token_hash=_hash_token(raw_token),
        guest_name=body.guest_name,
        expected_spoken_language=body.expected_spoken_language,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours),
        max_uses=body.max_uses,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    return InviteResponse(
        id=invite.id,
        token=raw_token,
        invite_url=f"https://meet.example.com/join/{raw_token}",
        guest_name=invite.guest_name,
        expires_at=invite.expires_at.isoformat(),
        max_uses=invite.max_uses,
    )


@router.delete("/api/meetings/{meeting_id}/invites/{invite_id}")
async def revoke_invite(
    meeting_id: uuid.UUID,
    invite_id: uuid.UUID,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    result = await db.execute(
        select(MeetingInvite).where(
            MeetingInvite.id == invite_id,
            MeetingInvite.meeting_id == meeting_id,
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "Invite revoked"}


# ──── Public routes ────


@router.get("/api/public/invites/{token}", response_model=InvitePreviewResponse)
async def preview_invite(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitePreviewResponse:
    token_hash = _hash_token(token)
    result = await db.execute(
        select(MeetingInvite).where(MeetingInvite.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    now = datetime.now(timezone.utc)
    is_valid = (
        invite.revoked_at is None
        and invite.expires_at > now
        and invite.use_count < invite.max_uses
    )

    # Fetch meeting title
    meeting_result = await db.execute(select(Meeting).where(Meeting.id == invite.meeting_id))
    meeting = meeting_result.scalar_one_or_none()
    if not meeting or meeting.status == "ended":
        is_valid = False

    return InvitePreviewResponse(
        guest_name=invite.guest_name,
        meeting_title=meeting.title if meeting else "Unknown",
        expected_spoken_language=invite.expected_spoken_language,
        expires_at=invite.expires_at.isoformat(),
        is_valid=is_valid,
    )


@router.post("/api/public/invites/{token}/join", response_model=JoinResponse)
async def join_with_invite(
    token: str,
    body: JoinRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JoinResponse:
    token_hash = _hash_token(token)
    result = await db.execute(
        select(MeetingInvite).where(MeetingInvite.token_hash == token_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")

    now = datetime.now(timezone.utc)

    if invite.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has been revoked")

    if invite.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite has expired")

    if invite.use_count >= invite.max_uses:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Invite usage limit reached")

    meeting_result = await db.execute(select(Meeting).where(Meeting.id == invite.meeting_id))
    meeting = meeting_result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if meeting.status == "ended":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Meeting has ended")

    # Increment usage
    invite.use_count += 1
    await db.commit()

    guest_identity = f"guest_{secrets.token_hex(8)}"

    return JoinResponse(
        meeting_id=meeting.id,
        guest_identity=guest_identity,
        role="guest",
        caption_access=False,
    )
