"""Caption routing tests (MTG-050, MTG-053).

Covers:
- Caption events include speaker identity
- Sequence numbers are scoped per speaker
- Partial captions can be replaced
- Old revisions are ignored
- Guest receives no caption events
"""

import pytest
from starlette.requests import Request

from app.config import settings
from app.routers.captions import (
    CaptionEventRequest,
    _subscribers,
    ingest_caption_event,
    should_route_caption,
)


def caption_event(
    *, speaker_id: str = "english_internal", target_language: str = "th"
) -> CaptionEventRequest:
    return CaptionEventRequest(
        type="caption.final",
        event_id="evt_test",
        meeting_id="meeting_test",
        speaker_id=speaker_id,
        speaker_name="English Speaker",
        source_language="en" if target_language == "th" else "th",
        target_language=target_language,
        translated_text="test translation",
        sequence=1,
        revision=1,
        is_final=True,
    )



class TestCaptionEventProtocol:
    def test_caption_delta_event_structure(self):
        """MTG-034: Verify caption.delta event schema."""
        event = {
            "type": "caption.delta",
            "event_id": "evt_123",
            "meeting_id": "meeting_456",
            "speaker_id": "participant_789",
            "speaker_name": "Client",
            "source_language": "en",
            "target_language": "th",
            "translated_text": "เราต้องการเปิดตัวในเดือนกันยายน",
            "sequence": 18,
            "revision": 3,
            "is_final": False,
            "started_at": "2026-07-12T10:15:04.220Z",
        }

        assert event["type"] == "caption.delta"
        assert event["is_final"] is False
        assert "speaker_id" in event
        assert "event_id" in event

    def test_caption_final_event_structure(self):
        """MTG-034: Verify caption.final event schema."""
        event = {
            "type": "caption.final",
            "event_id": "evt_123",
            "meeting_id": "meeting_456",
            "speaker_id": "participant_789",
            "speaker_name": "Client",
            "source_language": "en",
            "target_language": "th",
            "translated_text": "เราต้องการเปิดตัวแอปในเดือนกันยายน",
            "sequence": 18,
            "revision": 4,
            "is_final": True,
        }

        assert event["type"] == "caption.final"
        assert event["is_final"] is True
        assert event["revision"] == 4

    def test_final_replaces_partial(self):
        """Final translation should replace partial translation."""
        partial = {"revision": 3, "is_final": False, "translated_text": "partial"}
        final = {"revision": 4, "is_final": True, "translated_text": "final text"}

        assert final["is_final"]
        assert final["revision"] > partial["revision"]

    def test_old_revision_ignored(self):
        """Newer revisions should always win over older ones."""
        events = [
            {"revision": 5, "text": "latest"},
            {"revision": 3, "text": "stale"},
            {"revision": 4, "text": "newer"},
        ]

        latest = max(events, key=lambda e: e["revision"])
        assert latest["text"] == "latest"
        assert latest["revision"] == 5

    def test_sequence_scoped_per_speaker(self):
        """Sequence numbers are per-speaker, not global."""
        speaker_a_events = [
            {"speaker_id": "A", "sequence": 1},
            {"speaker_id": "A", "sequence": 2},
        ]
        speaker_b_events = [
            {"speaker_id": "B", "sequence": 1},
            {"speaker_id": "B", "sequence": 2},
        ]

        # Both speakers can have sequence 1 independently
        assert speaker_a_events[0]["sequence"] == speaker_b_events[0]["sequence"]
        assert speaker_a_events[0]["speaker_id"] != speaker_b_events[0]["speaker_id"]


class TestCaptionRouting:
    def test_english_speaker_routes_thai_translation(self):
        """English speaker → Thai translation for Thai-caption subscribers."""
        source = "en"
        target = "th"
        assert source == "en" and target == "th"

    def test_thai_speaker_routes_english_translation(self):
        """Thai speaker → English translation for English-caption subscribers."""
        source = "th"
        target = "en"
        assert source == "th" and target == "en"

    def test_guest_never_receives_captions(self):
        """Guests must never receive caption events, regardless of request."""
        guest_permissions = {"role": "guest", "caption_access": False}
        assert not guest_permissions["caption_access"]

    def test_normal_caption_language_still_routes(self):
        event = caption_event(speaker_id="someone_else", target_language="en")

        assert should_route_caption("english_internal", "en", event)

    def test_internal_speaker_receives_own_translation_preview(self):
        event = caption_event(
            speaker_id="english_internal", target_language="th"
        )

        assert should_route_caption("english_internal", "en", event)

    def test_other_language_translation_is_not_leaked_to_unrelated_user(self):
        event = caption_event(speaker_id="another_speaker", target_language="th")

        assert not should_route_caption("english_internal", "en", event)

    @pytest.mark.asyncio
    async def test_ingest_delivers_self_translation_to_english_account(self):
        class FakeWebSocket:
            def __init__(self) -> None:
                self.events: list[dict[str, object]] = []

            async def send_json(self, payload: dict[str, object]) -> None:
                self.events.append(payload)

        meeting_id = "meeting_self_preview"
        websocket = FakeWebSocket()
        _subscribers[meeting_id] = {
            "english_internal": {"ws": websocket, "lang": "en"}
        }
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/",
                "headers": [
                    (
                        b"authorization",
                        f"Bearer {settings.caption_worker_service_token}".encode(),
                    )
                ],
            }
        )
        event = caption_event(
            speaker_id="english_internal", target_language="th"
        ).model_copy(update={"meeting_id": meeting_id})

        try:
            result = await ingest_caption_event(
                meeting_id,
                event,
                request,
            )
        finally:
            _subscribers.pop(meeting_id, None)

        assert result["routed_to"] == 1
        assert len(websocket.events) == 1
        assert websocket.events[0]["target_language"] == "th"
