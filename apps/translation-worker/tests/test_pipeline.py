from __future__ import annotations

import asyncio

import pytest

from pipeline import (
    ParticipantAudioPipeline,
    TranscriptionResult,
    TranslationResult,
    should_use_direct_translation,
)


class FakeTranscriptionProvider:
    def __init__(self, commit_result: bool = False) -> None:
        self.language: str | None = None
        self.results: asyncio.Queue[TranscriptionResult | Exception] = asyncio.Queue()
        self.audio: list[bytes] = []
        self.commit_result = commit_result
        self.committed = False
        self.stopped = False

    async def start(self, language: str) -> None:
        self.language = language

    async def append_audio(self, pcm: bytes) -> None:
        self.audio.append(pcm)

    async def receive(self) -> TranscriptionResult:
        result = await self.results.get()
        if isinstance(result, Exception):
            raise result
        return result

    async def commit_pending(self) -> bool:
        self.committed = True
        return self.commit_result

    async def stop(self) -> None:
        self.stopped = True


class FakeTranslationProvider:
    def __init__(self) -> None:
        self.partial_calls: list[tuple[str, int]] = []
        self.closed = False

    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult:
        self.partial_calls.append((text, revision))
        return TranslationResult(
            text="สวัสดี",
            source_language=source_language,
            target_language=target_language,
        )

    async def translate_final(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult:
        assert text == "Hello"
        return TranslationResult(
            text="สวัสดี",
            source_language=source_language,
            target_language=target_language,
        )

    async def close(self) -> None:
        self.closed = True


def test_hybrid_provider_uses_only_validated_direct_sources(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_REALTIME_TRANSLATE_SOURCE_LANGUAGES", "en")

    assert should_use_direct_translation("openai-hybrid", "en")
    assert not should_use_direct_translation("openai-hybrid", "th")
    assert should_use_direct_translation("openai-realtime-translate", "th")
    assert not should_use_direct_translation("openai-transcribe-then-translate", "en")


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

    assert [caption["event_id"] for caption in delivered] == ["speaker-1:last-item"]


@pytest.mark.asyncio
async def test_direct_translation_streams_revision_safe_caption() -> None:
    direct = FakeTranscriptionProvider()
    delivered: list[dict[str, object]] = []
    delivered_twice = asyncio.Event()

    async def caption_sink(event: dict[str, object]) -> None:
        delivered.append(event)
        if len(delivered) == 2:
            delivered_twice.set()

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="en",
        caption_language="th",
        caption_sink=caption_sink,
        realtime_translation=direct,
        final_wait_seconds=0,
    )

    await pipeline.start()
    await direct.results.put(
        TranscriptionResult(
            text="สวัส",
            is_final=False,
            item_id="stream-1",
            language="th",
        )
    )
    await direct.results.put(
        TranscriptionResult(
            text="สวัสดี",
            is_final=True,
            item_id="stream-1",
            language="th",
        )
    )
    await asyncio.wait_for(delivered_twice.wait(), timeout=1)
    await pipeline.finish()

    assert [event["type"] for event in delivered] == [
        "caption.delta",
        "caption.final",
    ]
    assert [event["event_id"] for event in delivered] == [
        "speaker-1:stream-1",
        "speaker-1:stream-1",
    ]
    assert [event["sequence"] for event in delivered] == [1, 1]
    assert [event["revision"] for event in delivered] == [1, 2]
    assert [event["translated_text"] for event in delivered] == [
        "สวัส",
        "สวัสดี",
    ]


@pytest.mark.asyncio
async def test_direct_start_failure_uses_transcribe_then_translate_fallback() -> None:
    class FailingDirectProvider(FakeTranscriptionProvider):
        async def start(self, language: str) -> None:
            raise ConnectionError("direct provider unavailable")

    direct = FailingDirectProvider()
    fallback = FakeTranscriptionProvider()
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
        realtime_translation=direct,
        transcription=fallback,
        translation=FakeTranslationProvider(),
        final_wait_seconds=0,
    )

    await pipeline.start()
    await fallback.results.put(
        TranscriptionResult(
            text="Hello",
            is_final=True,
            item_id="fallback-1",
            language="en",
        )
    )
    await asyncio.wait_for(delivered_event.wait(), timeout=1)
    await pipeline.finish()

    assert direct.stopped
    assert fallback.language == "en"
    assert delivered[0]["type"] == "caption.final"
    assert delivered[0]["event_id"] == "speaker-1:fallback-1"


@pytest.mark.asyncio
async def test_direct_runtime_failure_switches_only_that_pipeline_to_fallback() -> None:
    direct = FakeTranscriptionProvider()
    fallback = FakeTranscriptionProvider()
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
        realtime_translation=direct,
        transcription=fallback,
        translation=FakeTranslationProvider(),
        final_wait_seconds=0,
    )

    await pipeline.start()
    await direct.results.put(ConnectionError("direct session closed"))
    for _ in range(20):
        if fallback.language == "en":
            break
        await asyncio.sleep(0.01)
    await fallback.results.put(
        TranscriptionResult(
            text="Hello",
            is_final=True,
            item_id="fallback-runtime-1",
            language="en",
        )
    )
    await asyncio.wait_for(delivered_event.wait(), timeout=1)
    await pipeline.finish()

    assert direct.stopped
    assert fallback.language == "en"
    assert delivered[0]["event_id"] == "speaker-1:fallback-runtime-1"


@pytest.mark.asyncio
async def test_late_final_revision_keeps_original_caption_sequence() -> None:
    direct = FakeTranscriptionProvider()
    delivered: list[dict[str, object]] = []
    delivered_twice = asyncio.Event()

    async def caption_sink(event: dict[str, object]) -> None:
        delivered.append(event)
        if len(delivered) == 2:
            delivered_twice.set()

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="th",
        caption_language="en",
        caption_sink=caption_sink,
        realtime_translation=direct,
        final_wait_seconds=0,
    )

    await pipeline.start()
    await direct.results.put(
        TranscriptionResult(
            text="Software",
            is_final=True,
            item_id="stream-1",
            language="en",
        )
    )
    await direct.results.put(
        TranscriptionResult(
            text="Software update",
            is_final=True,
            item_id="stream-1",
            language="en",
        )
    )
    await asyncio.wait_for(delivered_twice.wait(), timeout=1)
    await pipeline.finish()

    assert [event["sequence"] for event in delivered] == [1, 1]
    assert [event["revision"] for event in delivered] == [1, 2]
    assert [event["event_id"] for event in delivered] == [
        "speaker-1:stream-1",
        "speaker-1:stream-1",
    ]


@pytest.mark.asyncio
async def test_fallback_partial_is_replaced_by_final_translation() -> None:
    transcription = FakeTranscriptionProvider()
    translation = FakeTranslationProvider()
    delivered: list[dict[str, object]] = []
    partial_delivered = asyncio.Event()
    final_delivered = asyncio.Event()

    async def caption_sink(event: dict[str, object]) -> None:
        delivered.append(event)
        if event["is_final"]:
            final_delivered.set()
        else:
            partial_delivered.set()

    pipeline = ParticipantAudioPipeline(
        participant_id="speaker-1",
        participant_name="Speaker",
        spoken_language="en",
        caption_language="th",
        caption_sink=caption_sink,
        transcription=transcription,
        translation=translation,
        partial_debounce_seconds=0.01,
        partial_min_chars=1,
        final_wait_seconds=0,
    )

    await pipeline.start()
    await transcription.results.put(
        TranscriptionResult(
            text="Hello",
            is_final=False,
            item_id="item-1",
            language="en",
        )
    )
    await asyncio.wait_for(partial_delivered.wait(), timeout=1)
    await transcription.results.put(
        TranscriptionResult(
            text="Hello",
            is_final=True,
            item_id="item-1",
            language="en",
        )
    )
    await asyncio.wait_for(final_delivered.wait(), timeout=1)
    await pipeline.finish()

    assert [event["type"] for event in delivered] == [
        "caption.delta",
        "caption.final",
    ]
    assert [event["event_id"] for event in delivered] == [
        "speaker-1:item-1",
        "speaker-1:item-1",
    ]
    assert [event["sequence"] for event in delivered] == [1, 1]
    assert [event["revision"] for event in delivered] == [1, 2]
    assert translation.partial_calls == [("Hello", 1)]
    assert translation.closed


@pytest.mark.asyncio
async def test_stale_fallback_partial_cannot_overwrite_newer_text() -> None:
    class SlowFirstTranslation(FakeTranslationProvider):
        async def translate_partial(
            self,
            text: str,
            source_language: str,
            target_language: str,
            revision: int,
        ) -> TranslationResult:
            await asyncio.sleep(0.2 if text == "Hel" else 0.01)
            return TranslationResult(
                text="old" if text == "Hel" else "new",
                source_language=source_language,
                target_language=target_language,
            )

    transcription = FakeTranscriptionProvider()
    translation = SlowFirstTranslation()
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
        translation=translation,
        partial_debounce_seconds=0,
        partial_min_chars=1,
        final_wait_seconds=0,
    )

    await pipeline.start()
    await transcription.results.put(TranscriptionResult("Hel", False, "item-1", "en"))
    await asyncio.sleep(0.02)
    await transcription.results.put(TranscriptionResult("Hello", False, "item-1", "en"))
    await asyncio.wait_for(delivered_event.wait(), timeout=1)
    await asyncio.sleep(0.25)
    await pipeline.finish()

    assert [event["translated_text"] for event in delivered] == ["new"]
