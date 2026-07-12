"""
Participant audio pipeline: LiveKit → normalize → OpenAI → translate → captions.

Translates only completed transcription items. One caption queue owner:
the worker drains and delivers through flush_captions().
"""

import array
import asyncio
import logging
import os
import time
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


class AudioNormalizer:
    MAX_BUFFER_SIZE = 1024 * 512

    def __init__(self) -> None:
        self._buffer: list[bytes] = []
        self._size: int = 0

    async def append_frame(self, data: bytes, sample_rate: int, channels: int) -> None:
        if self._size + len(data) > self.MAX_BUFFER_SIZE:
            if self._buffer:
                self._size -= len(self._buffer.pop(0))
        self._buffer.append(data)
        self._size += len(data)

    async def drain(self) -> bytes:
        out = b"".join(self._buffer)
        self._buffer.clear()
        self._size = 0
        return out

    @property
    def buffer_size(self) -> int:
        return self._size


class SilenceDetector:
    def __init__(self, timeout_ms: int = 5000) -> None:
        self._timeout = timeout_ms
        self._last: float = 0.0

    def update(self, data: bytes) -> None:
        if len(data) >= 2:
            samples = array.array("h", data)
            if len(samples) > 0:
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                if rms > 100:
                    self._last = time.monotonic() * 1000

    def is_silent(self) -> bool:
        return (time.monotonic() * 1000 - self._last) > self._timeout


class RealtimeTranscriptionProvider:
    async def start(self, language: str) -> None: ...
    async def append_audio(self, pcm: bytes) -> None: ...
    async def stop(self) -> None: ...
    async def receive(self) -> TranscriptionResult: ...
    async def commit_pending(self) -> None: ...


class TranslationProvider:
    async def translate_final(self, text: str, source: str, target: str) -> TranslationResult: ...


@dataclass
class ParticipantAudioPipeline:
    participant_id: str
    participant_name: str
    spoken_language: str
    caption_language: str

    _normalizer: AudioNormalizer = field(default_factory=AudioNormalizer)
    _silence: SilenceDetector = field(default_factory=SilenceDetector)
    _transcription: Optional[RealtimeTranscriptionProvider] = None
    _translation: Optional[TranslationProvider] = None
    _state: PipelineState = PipelineState.IDLE
    _seq: int = 0
    _rev: int = 0
    _queue: asyncio.Queue[dict] = field(default_factory=asyncio.Queue)
    _consumer: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._state = PipelineState.STARTING
        logger.info("Pipeline %s: %s→%s", self.participant_name, self.spoken_language, self.caption_language)

        api_key = os.environ.get("OPENAI_API_KEY", "")
        tmodel = os.environ.get("OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-realtime-whisper")
        xmodel = os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4o-mini")

        from openai_transcribe import OpenAIRealtimeTranscribeProvider
        self._transcription = OpenAIRealtimeTranscribeProvider(api_key, model=tmodel)
        await self._transcription.start(self.spoken_language)

        from translators import OpenAITranscribeThenTranslateProvider
        self._translation = OpenAITranscribeThenTranslateProvider(api_key, translation_model=xmodel)

        self._consumer = asyncio.create_task(self._consume())
        self._state = PipelineState.RUNNING

    async def process_audio_frame(self, data: bytes, sr: int, ch: int) -> None:
        if self._state != PipelineState.RUNNING:
            return
        self._silence.update(data)
        if self._silence.is_silent():
            return
        await self._normalizer.append_frame(data, sr, ch)
        chunk = await self._normalizer.drain()
        if chunk and self._transcription:
            await self._transcription.append_audio(chunk)

    async def _consume(self) -> None:
        """Translate only final transcripts. Put into queue for worker delivery."""
        try:
            while self._state == PipelineState.RUNNING and self._transcription:
                try:
                    result = await asyncio.wait_for(self._transcription.receive(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not result.is_final or not self._translation:
                    continue

                self._rev += 1
                self._seq += 1
                translation = await self._translation.translate_final(
                    result.text, self.spoken_language, self.caption_language,
                )
                await self._queue.put({
                    "type": "caption.final",
                    "event_id": result.item_id,
                    "meeting_id": "",
                    "speaker_id": self.participant_id,
                    "speaker_name": self.participant_name,
                    "source_language": self.spoken_language,
                    "target_language": self.caption_language,
                    "translated_text": translation.text,
                    "sequence": self._seq,
                    "revision": self._rev,
                    "is_final": True,
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Consumer error %s: %s", self.participant_name, e)

    def drain_captions(self) -> list[dict]:
        """Non-blocking drain of the caption queue."""
        out = []
        while not self._queue.empty():
            try:
                out.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return out

    async def stop(self) -> None:
        """Graceful shutdown: commit pending audio, drain final captions, close."""
        self._state = PipelineState.STOPPING

        if self._transcription:
            await self._transcription.commit_pending()

        # Wait briefly for final transcript and translation
        await asyncio.sleep(2.0)

        if self._consumer:
            self._consumer.cancel()
            try:
                await self._consumer
            except asyncio.CancelledError:
                pass
            self._consumer = None

        if self._transcription:
            await self._transcription.stop()
        self._state = PipelineState.IDLE
        logger.info("Stopped pipeline: %s", self.participant_name)

    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
