"""Meeting API routes (MTG-020)."""

import secrets
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_internal_role
from app.database import get_db
from app.models.meeting import Meeting
from app.models.user import User

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


class CreateMeetingRequest(BaseModel):
    title: str
    guest_spoken_language: str = "en"
    expires_in_hours: int = 24


class MeetingResponse(BaseModel):
    id: uuid.UUID
    room_name: str
    title: str
    status: str
    created_by: uuid.UUID
    created_at: datetime | None

    model_config = {"from_attributes": True}


def _generate_room_name() -> str:
    """Generate a cryptographically random room name."""
    return f"room_{secrets.token_hex(16)}"


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    body: CreateMeetingRequest,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Meeting:
    if body.guest_spoken_language not in ("en", "th"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="guest_spoken_language must be 'en' or 'th'",
        )

    meeting = Meeting(
        room_name=_generate_room_name(),
        title=body.title,
        status="created",
        created_by=user.id,
    )
    db.add(meeting)
    await db.commit()
    await db.refresh(meeting)
    return meeting


@router.get("", response_model=list[MeetingResponse])
async def list_meetings(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Meeting]:
    result = await db.execute(
        select(Meeting).order_by(Meeting.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Meeting:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


@router.post("/{meeting_id}/end", response_model=MeetingResponse)
async def end_meeting(
    meeting_id: uuid.UUID,
    user: Annotated[User, Depends(require_internal_role)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Meeting:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    if meeting.status == "ended":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meeting already ended",
        )

    meeting.status = "ended"
    await db.commit()
    await db.refresh(meeting)
    return meeting
