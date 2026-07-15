"""Tests for the authoritative 60-minute meeting lifecycle."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.config import settings
from app.meeting_lifecycle import meeting_deadline, meeting_is_expired
from app.routers.meetings import MeetingResponse


def test_unstarted_meeting_expires_from_creation() -> None:
    created_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    meeting = SimpleNamespace(
        status="created", created_at=created_at, started_at=None, ended_at=None
    )

    assert meeting_deadline(meeting) == created_at + timedelta(
        minutes=settings.meeting_max_duration_minutes
    )
    assert not meeting_is_expired(meeting, created_at + timedelta(minutes=59))
    assert meeting_is_expired(meeting, created_at + timedelta(minutes=60))


def test_active_meeting_gets_full_hour_from_first_join() -> None:
    created_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    started_at = created_at + timedelta(minutes=25)
    meeting = SimpleNamespace(
        status="active", created_at=created_at, started_at=started_at, ended_at=None
    )

    assert meeting_deadline(meeting) == started_at + timedelta(minutes=60)
    assert not meeting_is_expired(meeting, started_at + timedelta(minutes=59, seconds=59))
    assert meeting_is_expired(meeting, started_at + timedelta(minutes=60))


def test_meeting_response_exposes_deadline_and_duration() -> None:
    created_at = datetime(2026, 7, 15, 10, 0, tzinfo=timezone.utc)
    response = MeetingResponse(
        id=uuid.uuid4(),
        room_name="room_test",
        title="Test consultation",
        status="created",
        created_by=uuid.uuid4(),
        created_at=created_at,
        started_at=None,
        ended_at=None,
    ).model_dump()

    assert response["max_duration_minutes"] == 60
    assert response["auto_end_at"] == created_at + timedelta(minutes=60)
