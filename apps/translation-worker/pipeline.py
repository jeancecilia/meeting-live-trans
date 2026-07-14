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
    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult: ...

    async def translate_final(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult: ...

    async def close(self) -> None: ...


def should_use_direct_translation(provider_name: str, spoken_language: str) -> bool:
    """Select the direct provider only for explicitly validated directions."""
    if provider_name == "openai-realtime-translate":
        return True
    if provider_name != "openai-hybrid":
        return False
    validated_sources = {
        language.strip().lower()
        for language in os.environ.get(
            "OPENAI_REALTIME_TRANSLATE_SOURCE_LANGUAGES", "en"
        ).split(",")
        if language.strip()
    }
    return spoken_language in validated_sources


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
        return (time.monotonic() * 1_000 - self._last_signal_ms) <= self._timeout_ms

    def is_silent(self) -> bool:
        return not self.should_forward()


class ParticipantAudioPipeline:
    """Translate one participant microphone with direct streaming and fallback."""

    def __init__(
        self,
        *,
        participant_id: str,
        participant_name: str,
        spoken_language: str,
        caption_language: str,
        caption_sink: CaptionSink | None = None,
        error_sink: ErrorSink | None = None,
        realtime_translation: RealtimeTranscriptionProvider | None = None,
        transcription: RealtimeTranscriptionProvider | None = None,
        translation: TranslationProvider | None = None,
        final_wait_seconds: float = 5.0,
        partial_debounce_seconds: float | None = None,
        partial_min_chars: int | None = None,
    ) -> None:
        self.participant_id = participant_id
        self.participant_name = participant_name
        self.spoken_language = spoken_language
        self.caption_language = caption_language
        self._caption_sink = caption_sink or _discard_caption
        self._error_sink = error_sink
        self._direct_candidate = realtime_translation
        self._fallback_transcription = transcription
        self._fallback_translation = translation
        self._audio_provider: RealtimeTranscriptionProvider | None = None
        self._translation: TranslationProvider | None = None
        self._uses_direct_output = False
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
        self._provider_lock = asyncio.Lock()
        self._last_item_id = ""
        self._last_item_sequence = 0
        self._partial_debounce_seconds = (
            partial_debounce_seconds
            if partial_debounce_seconds is not None
            else int(os.environ.get("TRANSLATION_PARTIAL_DEBOUNCE_MS", "150")) / 1_000
        )
        self._partial_min_chars = (
            partial_min_chars
            if partial_min_chars is not None
            else int(os.environ.get("TRANSLATION_PARTIAL_MIN_CHARS", "8"))
        )
        self._partial_revision = 0
        self._partial_task: asyncio.Task[None] | None = None
        self._caption_emit_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._state != PipelineState.IDLE:
            return

        self._state = PipelineState.STARTING
        provider_name = (
            os.environ.get("TRANSLATION_PROVIDER", "openai-hybrid").strip().lower()
        )
        use_direct = self._direct_candidate is not None or (
            self._fallback_transcription is None
            and should_use_direct_translation(provider_name, self.spoken_language)
        )

        if use_direct:
            if self._direct_candidate is None:
                from openai_translate import OpenAIRealtimeTranslateProvider

                self._direct_candidate = OpenAIRealtimeTranslateProvider(
                    api_key=os.environ.get("OPENAI_API_KEY", ""),
                    target_language=self.caption_language,
                    model=os.environ.get(
                        "OPENAI_REALTIME_TRANSLATE_MODEL", "gpt-realtime-translate"
                    ),
                )
            try:
                await self._direct_candidate.start(self.spoken_language)
                self._audio_provider = self._direct_candidate
                self._uses_direct_output = True
            except Exception as exc:
                logger.warning(
                    "Direct translation unavailable; starting fallback: "
                    "participant=%s error=%s",
                    self.participant_id,
                    type(exc).__name__,
                )
                await self._direct_candidate.stop()
                await self._start_fallback()
        elif (
            provider_name
            not in {
                "openai-hybrid",
                "openai-transcribe-then-translate",
            }
            and self._fallback_transcription is None
        ):
            self._state = PipelineState.ERROR
            raise ValueError(f"Unsupported TRANSLATION_PROVIDER: {provider_name}")
        else:
            await self._start_fallback()

        self._state = PipelineState.RUNNING
        self._consumer_task = asyncio.create_task(
            self._consume_outputs(),
            name=f"caption-consumer-{self.participant_id}",
        )
        logger.info(
            "Pipeline started: participant=%s source=%s target=%s provider=%s",
            self.participant_id,
            self.spoken_language,
            self.caption_language,
            (
                "openai-realtime-translate"
                if self._uses_direct_output
                else "openai-transcribe-then-translate"
            ),
        )

    async def _start_fallback(self) -> None:
        if self._fallback_transcription is None:
            from openai_transcribe import OpenAIRealtimeTranscribeProvider

            self._fallback_transcription = OpenAIRealtimeTranscribeProvider(
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                model=os.environ.get(
                    "OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper"
                ),
            )
        if self._fallback_translation is None:
            from translators import OpenAITextTranslationProvider

            self._fallback_translation = OpenAITextTranslationProvider(
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                model=os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini"),
            )

        await self._fallback_transcription.start(self.spoken_language)
        self._audio_provider = self._fallback_transcription
        self._translation = self._fallback_translation
        self._uses_direct_output = False

    async def process_audio_frame(
        self, pcm: bytes, sample_rate: int, channels: int
    ) -> None:
        if self._state != PipelineState.RUNNING or self._audio_provider is None:
            return
        if sample_rate != 24_000 or channels != 1:
            raise ValueError(
                f"Expected mono 24 kHz PCM, received {channels} channel(s) at {sample_rate} Hz"
            )

        self._silence.update(pcm)
        if self._silence.should_forward():
            try:
                async with self._provider_lock:
                    assert self._audio_provider is not None
                    await self._audio_provider.append_audio(pcm)
            except Exception:
                if self._uses_direct_output:
                    logger.warning(
                        "Direct translation audio stream interrupted: participant=%s",
                        self.participant_id,
                    )
                    return
                raise

    async def _consume_outputs(self) -> None:
        while self._state in {PipelineState.RUNNING, PipelineState.STOPPING}:
            provider = self._audio_provider
            if provider is None:
                return
            try:
                output = await provider.receive()
            except asyncio.CancelledError:
                raise
            except Exception:
                if self._uses_direct_output and provider is self._audio_provider:
                    if await self._switch_to_fallback(provider):
                        continue
                await self._report_caption_error()
                continue

            if provider is not self._audio_provider or not output.text.strip():
                continue

            try:
                if self._uses_direct_output:
                    await self._emit_caption(
                        output.text,
                        output.item_id,
                        is_final=output.is_final,
                    )
                    continue

                if self._translation is None:
                    continue
                if not output.is_final:
                    self._schedule_partial_translation(output)
                    continue
                translation = await self._translation.translate_final(
                    output.text,
                    self.spoken_language,
                    self.caption_language,
                )
                self._partial_revision += 1
                await self._emit_caption(
                    translation.text,
                    output.item_id,
                    is_final=True,
                )
                if self._partial_task is not None:
                    if not self._partial_task.done():
                        self._partial_task.cancel()
                    self._partial_task = None
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Caption generation failed: participant=%s",
                    self.participant_id,
                )
                await self._report_caption_error()

    def _schedule_partial_translation(self, output: TranscriptionResult) -> None:
        if len(output.text.strip()) < self._partial_min_chars:
            return
        self._partial_revision += 1
        revision = self._partial_revision
        if self._partial_task is not None:
            self._partial_task.cancel()
        self._partial_task = asyncio.create_task(
            self._translate_partial_after_debounce(output, revision),
            name=f"partial-translation-{self.participant_id}",
        )

    async def _translate_partial_after_debounce(
        self, output: TranscriptionResult, revision: int
    ) -> None:
        try:
            await asyncio.sleep(self._partial_debounce_seconds)
            if self._translation is None:
                return
            translation = await self._translation.translate_partial(
                output.text,
                self.spoken_language,
                self.caption_language,
                revision,
            )
            async with self._caption_emit_lock:
                if (
                    revision != self._partial_revision
                    or self._uses_direct_output
                    or self._state
                    not in {PipelineState.RUNNING, PipelineState.STOPPING}
                ):
                    return
                await self._emit_caption_locked(
                    translation.text,
                    output.item_id,
                    is_final=False,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "Partial translation failed: participant=%s",
                self.participant_id,
            )

    async def _switch_to_fallback(
        self, failed_provider: RealtimeTranscriptionProvider
    ) -> bool:
        try:
            async with self._provider_lock:
                if self._audio_provider is not failed_provider:
                    return True
                await failed_provider.stop()
                await self._start_fallback()
            logger.warning(
                "Translation provider switched to fallback: participant=%s",
                self.participant_id,
            )
            return True
        except Exception:
            logger.exception(
                "Translation fallback failed to start: participant=%s",
                self.participant_id,
            )
            return False

    async def _emit_caption(self, text: str, item_id: str, *, is_final: bool) -> None:
        async with self._caption_emit_lock:
            await self._emit_caption_locked(text, item_id, is_final=is_final)

    async def _emit_caption_locked(
        self, text: str, item_id: str, *, is_final: bool
    ) -> None:
        stable_item_id = item_id or uuid.uuid4().hex
        if stable_item_id == self._last_item_id:
            sequence = self._last_item_sequence
        else:
            self._sequence += 1
            sequence = self._sequence
            self._last_item_id = stable_item_id
            self._last_item_sequence = sequence
        self._revision += 1
        await self._caption_sink(
            {
                "type": "caption.final" if is_final else "caption.delta",
                "event_id": f"{self.participant_id}:{stable_item_id}",
                "speaker_id": self.participant_id,
                "speaker_name": self.participant_name,
                "source_language": self.spoken_language,
                "target_language": self.caption_language,
                "translated_text": text,
                "sequence": sequence,
                "revision": self._revision,
                "is_final": is_final,
            }
        )
        if is_final:
            self._caption_delivered.set()

    async def _report_caption_error(self) -> None:
        if self._error_sink is None or self._error_reported:
            return
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
        if self._audio_provider is not None:
            self._caption_delivered.clear()
            try:
                committed_audio = bool(await self._audio_provider.commit_pending())
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

        if self._partial_task is not None:
            self._partial_task.cancel()
            await asyncio.gather(self._partial_task, return_exceptions=True)
            self._partial_task = None

        if self._audio_provider is not None:
            await self._audio_provider.stop()
            self._audio_provider = None

        if self._translation is not None:
            close = getattr(self._translation, "close", None)
            if close is not None:
                await close()
            self._translation = None

        self._state = PipelineState.IDLE

    async def stop(self) -> None:
        """Backward-compatible lifecycle alias."""
        await self.finish()

    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
