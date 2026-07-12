"""
Participant audio pipeline — full end-to-end processing:
LiveKit audio frames → normalize → OpenAI transcription → translate → caption emit.

MTG-030, MTG-031, MTG-032, MTG-033, MTG-037
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("translation-worker.pipeline")


class PipelineState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class TranscriptionResult:
    text: str
    is_final: bool
    item_id: str
    language: str


@dataclass
class TranslationResult:
    text: str
    source_language: str
    target_language: str
    revision: int
    is_final: bool


# ──── Audio normalization ────

class AudioNormalizer:
    TARGET_SAMPLE_RATE = 24000
    TARGET_CHANNELS = 1
    MAX_BUFFER_SIZE = 1024 * 512

    def __init__(self) -> None:
        self._buffer: list[bytes] = []
        self._buffer_size: int = 0

    async def append_frame(self, pcm_data: bytes, sample_rate: int, channels: int) -> None:
        if self._buffer_size + len(pcm_data) > self.MAX_BUFFER_SIZE:
            if self._buffer:
                dropped = self._buffer.pop(0)
                self._buffer_size -= len(dropped)
        self._buffer.append(pcm_data)
        self._buffer_size += len(pcm_data)

    async def drain(self) -> bytes:
        data = b"".join(self._buffer)
        self._buffer.clear()
        self._buffer_size = 0
        return data

    @property
    def buffer_size(self) -> int:
        return self._buffer_size


# ──── Silence detection ────

class SilenceDetector:
    def __init__(self, silence_timeout_ms: int = 5000) -> None:
        self.silence_timeout_ms = silence_timeout_ms
        self._last_audio_time: float = 0.0
        self._silence_threshold: int = 100

    def update(self, pcm_data: bytes) -> None:
        if self._has_signal(pcm_data):
            import time
            self._last_audio_time = time.monotonic() * 1000

    def is_silent(self) -> bool:
        import time
        return (time.monotonic() * 1000 - self._last_audio_time) > self.silence_timeout_ms

    def _has_signal(self, pcm_data: bytes) -> bool:
        if len(pcm_data) < 2:
            return False
        import array
        samples = array.array("h", pcm_data)
        if len(samples) == 0:
            return False
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return rms > self._silence_threshold


# ──── Interfaces ────

class RealtimeTranscriptionProvider:
    async def start(self, language: str) -> None: ...
    async def append_audio(self, pcm: bytes) -> None: ...
    async def stop(self) -> None: ...
    async def receive(self) -> TranscriptionResult: ...


class TranslationProvider:
    async def translate_partial(self, text: str, source_language: str, target_language: str, revision: int) -> TranslationResult: ...
    async def translate_final(self, text: str, source_language: str, target_language: str) -> TranslationResult: ...


# ──── Participant pipeline (MTG-030) ────

@dataclass
class ParticipantAudioPipeline:
    participant_id: str
    participant_name: str
    spoken_language: str
    caption_language: str

    _normalizer: AudioNormalizer = field(default_factory=AudioNormalizer)
    _silence_detector: SilenceDetector = field(default_factory=SilenceDetector)
    _transcription_provider: Optional[RealtimeTranscriptionProvider] = None
    _translation_provider: Optional[TranslationProvider] = None
    _state: PipelineState = PipelineState.IDLE
    _sequence: int = 0
    _revision: int = 0
    _caption_queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    _consumer_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._state = PipelineState.STARTING
        logger.info("Starting pipeline for %s (lang: %s→%s)", self.participant_name, self.spoken_language, self.caption_language)

        api_key = os.environ.get("OPENAI_API_KEY", "")
        transcribe_model = os.environ.get("OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper")
        translate_model = os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini")

        # Create the real transcription provider
        from openai_transcribe import OpenAIRealtimeTranscribeProvider
        self._transcription_provider = OpenAIRealtimeTranscribeProvider(
            api_key=api_key,
            model=transcribe_model,
        )
        await self._transcription_provider.start(self.spoken_language)

        # Create the translation provider (fallback: transcribe then translate)
        from translators import OpenAITranscribeThenTranslateProvider
        self._translation_provider = OpenAITranscribeThenTranslateProvider(
            api_key=api_key,
            translation_model=translate_model,
        )

        # Start the transcript consumer task
        self._consumer_task = asyncio.create_task(self._consume_transcripts())

        self._state = PipelineState.RUNNING
        logger.info("Pipeline running for %s", self.participant_name)

    async def process_audio_frame(self, pcm_data: bytes, sample_rate: int, channels: int) -> None:
        if self._state != PipelineState.RUNNING:
            return

        self._silence_detector.update(pcm_data)
        if self._silence_detector.is_silent():
            return

        await self._normalizer.append_frame(pcm_data, sample_rate, channels)

        # Drain accumulated audio and send to transcription provider
        audio_chunk = await self._normalizer.drain()
        if audio_chunk and self._transcription_provider:
            await self._transcription_provider.append_audio(audio_chunk)

    async def _consume_transcripts(self) -> None:
        """Continuously receive transcripts, translate them, and emit captions."""
        try:
            while self._state == PipelineState.RUNNING and self._transcription_provider:
                try:
                    result = await asyncio.wait_for(
                        self._transcription_provider.receive(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                if not self._translation_provider:
                    continue

                self._revision += 1
                self._sequence += 1

                if result.is_final:
                    translation = await self._translation_provider.translate_final(
                        result.text,
                        self.spoken_language,
                        self.caption_language,
                    )
                    event = {
                        "type": "caption.final",
                        "event_id": result.item_id,
                        "meeting_id": "",
                        "speaker_id": self.participant_id,
                        "speaker_name": self.participant_name,
                        "source_language": self.spoken_language,
                        "target_language": self.caption_language,
                        "translated_text": translation.text,
                        "sequence": self._sequence,
                        "revision": self._revision,
                        "is_final": True,
                    }
                else:
                    translation = await self._translation_provider.translate_partial(
                        result.text,
                        self.spoken_language,
                        self.caption_language,
                        self._revision,
                    )
                    event = {
                        "type": "caption.delta",
                        "event_id": result.item_id,
                        "meeting_id": "",
                        "speaker_id": self.participant_id,
                        "speaker_name": self.participant_name,
                        "source_language": self.spoken_language,
                        "target_language": self.caption_language,
                        "translated_text": translation.text,
                        "sequence": self._sequence,
                        "revision": self._revision,
                        "is_final": False,
                    }

                await self._caption_queue.put(event)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Transcript consumer error for %s: %s", self.participant_name, e)

    async def flush_captions(self) -> list[dict]:
        captions = []
        while not self._caption_queue.empty():
            captions.append(await self._caption_queue.get())
        return captions

    async def stop(self) -> None:
        self._state = PipelineState.STOPPING
        if self._consumer_task:
            self._consumer_task.cancel()
            self._consumer_task = None
        if self._transcription_provider:
            await self._transcription_provider.stop()
        self._state = PipelineState.IDLE
        logger.info("Stopped pipeline for %s", self.participant_name)

    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
