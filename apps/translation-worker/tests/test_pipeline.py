from __future__ import annotations

import asyncio

import pytest

from pipeline import (
    ParticipantAudioPipeline,
    TranscriptionResult,
    TranslationResult,
)


class FakeTranscriptionProvider:
    def __init__(self, commit_result: bool = False) -> None:
        self.language: str | None = None
        self.results: asyncio.Queue[TranscriptionResult] = asyncio.Queue()
        self.audio: list[bytes] = []
        self.commit_result = commit_result
        self.committed = False
        self.stopped = False

    async def start(self, language: str) -> None:
        self.language = language

    async def append_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def receive(self) -> TranscriptionResult:
        return await self.results.get()

    async def commit_pending(self) -> bool:
        self.committed = True
        return self.commit_result

    async def stop(self) -> None:
        self.stopped = True


class FakeTranslationProvider:
    async def translate_final(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult:
        assert text == "Hello"
        return TranslationResult(
            text="สวัสดี",
            source_language=source_language,
            target_language=target_language,
        )


@pytest.mark.asyncio
async def test_final_transcript_produces_api_compatible_caption() -> None:
    transcription = FakeTranscriptionProvider()
    delivered: list[dict[str, object]] = []
    delivered_event = asyncio.Event()

    async def caption_sink(event: dict[str, object]) -> None:
        delivered.append(event)
        delivered_event.set()

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="en",
        caption_language="th",
        caption_sink=caption_sink,
        transcription=transcription,
        translation=FakeTranslationProvider(),
        final_wait_seconds=0,
    )

    await pipeline.start()
    await transcription.results.put(
        TranscriptionResult(
            text="Hello",
            is_final=True,
            item_id="item-123",
            language="en",
        )
    )
    await asyncio.wait_for(delivered_event.wait(), timeout=1)
    await pipeline.finish()

    assert transcription.language == "en"
    assert transcription.committed
    assert transcription.stopped
    assert delivered == [
        {
            "type": "caption.final",
            "event_id": "speaker-1:item-123",
            "speaker_id": "speaker-1",
            "speaker_name": "Speaker",
            "source_language": "en",
            "target_language": "th",
            "translated_text": "สวัสดี",
            "sequence": 1,
            "revision": 1,
            "is_final": True,
        }
    ]


@pytest.mark.asyncio
async def test_pipeline_requires_normalized_audio() -> None:
    async def caption_sink(_event: dict[str, object]) -> None:
        return None

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="en",
        caption_language="th",
        caption_sink=caption_sink,
        transcription=FakeTranscriptionProvider(),
        translation=FakeTranslationProvider(),
        final_wait_seconds=0,
    )
    await pipeline.start()

    with pytest.raises(ValueError, match="mono 24 kHz"):
        await pipeline.process_audio_frame(b"\x00\x00" * 100, 48_000, 2)

    await pipeline.finish()


@pytest.mark.asyncio
async def test_finish_waits_for_the_last_committed_caption() -> None:
    class CommitCompletesTranscription(FakeTranscriptionProvider):
        async def commit_pending(self) -> bool:
            await self.results.put(
                TranscriptionResult(
                    text="Hello",
                    is_final=True,
                    item_id="last-item",
                    language="en",
                )
            )
            return True

    transcription = CommitCompletesTranscription()
    delivered: list[dict[str, object]] = []

    async def caption_sink(event: dict[str, object]) -> None:
        delivered.append(event)

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="en",
        caption_language="th",
        caption_sink=caption_sink,
        transcription=transcription,
        translation=FakeTranslationProvider(),
        final_wait_seconds=1,
    )

    await pipeline.start()
    await pipeline.finish()

    assert [caption["event_id"] for caption in delivered] == [
        "speaker-1:last-item"
    ]
