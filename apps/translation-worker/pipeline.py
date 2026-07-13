"""Per-participant audio, transcription, translation, and caption pipeline."""

from __future__ import annotations

import array
import asyncio
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

logger = logging.getLogger("translation-worker.pipeline")

CaptionSink = Callable[[dict[str, object]], Awaitable[None]]
ErrorSink = Callable[[str], Awaitable[None]]


async def _discard_caption(_event: dict[str, object]) -> None:
    """Default sink used by compatibility and lifecycle-only callers."""


class AudioNormalizer:
    """Compatibility wrapper documenting the worker's bounded audio budget.

    LiveKit's ``AudioStream`` performs the actual resampling in ``main.py``.
    Keeping this small state object preserves the reliability-test contract
    without buffering an unbounded amount of call audio.
    """

    MAX_BUFFER_SIZE = 24_000 * 2 * 5

    def __init__(self) -> None:
        self.buffer_size = 0


class PipelineState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    is_final: bool
    item_id: str
    language: str


@dataclass(slots=True)
class TranslationResult:
    text: str
    source_language: str
    target_language: str


class RealtimeTranscriptionProvider(Protocol):
    async def start(self, language: str) -> None: ...

    async def append_audio(self, pcm: bytes) -> None: ...

    async def receive(self) -> TranscriptionResult: ...

    async def commit_pending(self) -> bool | None: ...

    async def stop(self) -> None: ...


class TranslationProvider(Protocol):
    async def translate_final(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult: ...


class SilenceDetector:
    """Allow trailing silence for commits, then suppress long silent periods."""

    def __init__(self, timeout_ms: int = 5_000, signal_threshold: float = 100.0):
        self._timeout_ms = timeout_ms
        self._signal_threshold = signal_threshold
        self._last_signal_ms = 0.0

    def update(self, pcm: bytes) -> None:
        if self.has_signal(pcm):
            self._last_signal_ms = time.monotonic() * 1_000

    def has_signal(self, pcm: bytes) -> bool:
        if len(pcm) < 2:
            return False
        samples = array.array("h")
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not samples:
            return False
        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
        return rms > self._signal_threshold

    def should_forward(self) -> bool:
        if self._last_signal_ms == 0:
            return False
        return (
            time.monotonic() * 1_000 - self._last_signal_ms
        ) <= self._timeout_ms

    def is_silent(self) -> bool:
        return not self.should_forward()


class ParticipantAudioPipeline:
    """Translate completed speech turns for one participant microphone."""

    def __init__(
        self,
        *,
        participant_id: str,
        participant_name: str,
        spoken_language: str,
        caption_language: str,
        caption_sink: CaptionSink | None = None,
        error_sink: ErrorSink | None = None,
        transcription: RealtimeTranscriptionProvider | None = None,
        translation: TranslationProvider | None = None,
        final_wait_seconds: float = 5.0,
    ) -> None:
        self.participant_id = participant_id
        self.participant_name = participant_name
        self.spoken_language = spoken_language
        self.caption_language = caption_language
        self._caption_sink = caption_sink or _discard_caption
        self._error_sink = error_sink
        self._transcription = transcription
        self._translation = translation
        self._final_wait_seconds = final_wait_seconds
        self._silence = SilenceDetector(
            timeout_ms=int(os.environ.get("TRANSLATION_SILENCE_TIMEOUT_MS", "5000"))
        )
        self._state = PipelineState.IDLE
        self._sequence = 0
        self._revision = 0
        self._consumer_task: asyncio.Task[None] | None = None
        self._caption_delivered = asyncio.Event()
        self._error_reported = False

    async def start(self) -> None:
        if self._state != PipelineState.IDLE:
            return

        self._state = PipelineState.STARTING
        if self._transcription is None:
            from openai_transcribe import OpenAIRealtimeTranscribeProvider

            self._transcription = OpenAIRealtimeTranscribeProvider(
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                model=os.environ.get(
                    "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-mini"
                ),
            )
        if self._translation is None:
            from translators import OpenAITextTranslationProvider

            self._translation = OpenAITextTranslationProvider(
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                model=os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini"),
            )

        try:
            await self._transcription.start(self.spoken_language)
        except Exception:
            self._state = PipelineState.ERROR
            raise

        self._state = PipelineState.RUNNING
        self._consumer_task = asyncio.create_task(
            self._consume_transcripts(),
            name=f"caption-consumer-{self.participant_id}",
        )
        logger.info(
            "Pipeline started: participant=%s source=%s target=%s",
            self.participant_id,
            self.spoken_language,
            self.caption_language,
        )

    async def process_audio_frame(
        self, pcm: bytes, sample_rate: int, channels: int
    ) -> None:
        if self._state != PipelineState.RUNNING or self._transcription is None:
            return
        if sample_rate != 24_000 or channels != 1:
            raise ValueError(
                f"Expected mono 24 kHz PCM, received {channels} channel(s) at {sample_rate} Hz"
            )

        self._silence.update(pcm)
        if self._silence.should_forward():
            await self._transcription.append_audio(pcm)

    async def _consume_transcripts(self) -> None:
        assert self._transcription is not None
        assert self._translation is not None

        while self._state in {PipelineState.RUNNING, PipelineState.STOPPING}:
            try:
                transcript = await self._transcription.receive()
                if not transcript.is_final or not transcript.text.strip():
                    continue

                translation = await self._translation.translate_final(
                    transcript.text,
                    self.spoken_language,
                    self.caption_language,
                )
                self._sequence += 1
                self._revision += 1
                event_id = transcript.item_id or uuid.uuid4().hex
                await self._caption_sink(
                    {
                        "type": "caption.final",
                        "event_id": f"{self.participant_id}:{event_id}",
                        "speaker_id": self.participant_id,
                        "speaker_name": self.participant_name,
                        "source_language": self.spoken_language,
                        "target_language": self.caption_language,
                        "translated_text": translation.text,
                        "sequence": self._sequence,
                        "revision": self._revision,
                        "is_final": True,
                    }
                )
                self._caption_delivered.set()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Caption generation failed: participant=%s",
                    self.participant_id,
                )
                if self._error_sink is not None and not self._error_reported:
                    self._error_reported = True
                    try:
                        await self._error_sink(
                            "Translation is temporarily unavailable. Please continue the call."
                        )
                    except Exception:
                        logger.exception("Failed to deliver pipeline error event")

    async def finish(self) -> None:
        if self._state == PipelineState.IDLE:
            return

        self._state = PipelineState.STOPPING
        committed_audio = False
        if self._transcription is not None:
            self._caption_delivered.clear()
            try:
                committed_audio = bool(await self._transcription.commit_pending())
            except Exception:
                logger.exception(
                    "Failed to commit pending audio: participant=%s",
                    self.participant_id,
                )

        if self._consumer_task is not None and not self._consumer_task.done():
            if committed_audio:
                try:
                    await asyncio.wait_for(
                        self._caption_delivered.wait(), timeout=self._final_wait_seconds
                    )
                except TimeoutError:
                    pass
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None

        if self._transcription is not None:
            await self._transcription.stop()

        self._state = PipelineState.IDLE

    async def stop(self) -> None:
        """Backward-compatible lifecycle alias."""
        await self.finish()

    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
