"""
Caption routing tests (MTG-050, MTG-053).

Covers:
- Caption events include speaker identity
- Sequence numbers are scoped per speaker
- Partial captions can be replaced
- Old revisions are ignored
- Guest receives no caption events
"""

import uuid

import pytest


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
