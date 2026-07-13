from __future__ import annotations

import json
import time

import pytest

from main import parse_participant_metadata
from openai_transcribe import OpenAIRealtimeTranscribeProvider


def test_json_participant_metadata() -> None:
    assert parse_participant_metadata(
        '{"app_role":"host","spoken_language":"th","caption_access":"true"}'
    ) == {
        "app_role": "host",
        "spoken_language": "th",
        "caption_access": "true",
    }


def test_legacy_participant_metadata_remains_supported() -> None:
    assert parse_participant_metadata(
        "app_role:guest; spoken_language:en; caption_access:false"
    ) == {
        "app_role": "guest",
        "spoken_language": "en",
        "caption_access": "false",
    }


@pytest.mark.asyncio
async def test_realtime_transcript_events_are_reconciled_by_item_id() -> None:
    provider = OpenAIRealtimeTranscribeProvider(api_key="test-key")
    provider._language = "en"

    await provider._dispatch(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "item-1",
            "delta": "Hel",
        }
    )
    await provider._dispatch(
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "item_id": "item-1",
            "delta": "lo",
        }
    )
    await provider._dispatch(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "item_id": "item-1",
            "transcript": "Hello",
        }
    )

    first = await provider.receive()
    second = await provider.receive()
    final = await provider.receive()

    assert first.text == "Hel" and not first.is_final
    assert second.text == "Hello" and not second.is_final
    assert final.text == "Hello" and final.is_final
    assert final.item_id == "item-1"


@pytest.mark.asyncio
async def test_realtime_audio_ignores_idle_silence_and_commits_after_speech() -> None:
    class FakeWebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send(self, payload: str) -> None:
            self.sent.append(json.loads(payload))

    provider = OpenAIRealtimeTranscribeProvider(api_key="test-key")
    websocket = FakeWebSocket()
    provider._connected = True
    provider._websocket = websocket

    silence = b"\x00\x00" * 2_400
    speech = b"\xff\x7f\x00\x80" * 1_200

    await provider.append_audio(silence)
    assert websocket.sent == []

    await provider.append_audio(speech)
    provider._last_signal_time = time.monotonic() - 1
    await provider.append_audio(silence)

    assert [message["type"] for message in websocket.sent] == [
        "input_audio_buffer.append",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
    ]
    assert provider._buffered_bytes == 0
