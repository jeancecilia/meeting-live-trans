"""
Participant audio pipeline — manages a single participant's audio stream
from LiveKit audio frames through normalization to OpenAI.

MTG-030, MTG-031, MTG-032, MTG-033
"""

import asyncio
import logging
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


class ProviderType(str, Enum):
    REALTIME_TRANSLATE = "openai-realtime-translate"
    TRANSCRIBE_THEN_TRANSLATE = "openai-transcribe-then-translate"


@dataclass
class TranscriptionResult:
    """Partial or final transcription from the realtime provider."""
    text: str
    is_final: bool
    item_id: str
    language: str


@dataclass
class TranslationResult:
    """Translated text result."""
    text: str
    source_language: str
    target_language: str
    revision: int
    is_final: bool


# ──── Audio normalization (MTG-031) ────


class AudioNormalizer:
    """
    Converts LiveKit audio frames to OpenAI-compatible format:
    mono PCM16 at 24 kHz.
    """

    TARGET_SAMPLE_RATE = 24000
    TARGET_CHANNELS = 1
    MAX_BUFFER_SIZE = 1024 * 512  # 512 KB max buffer

    def __init__(self) -> None:
        self._buffer: list[bytes] = []
        self._buffer_size: int = 0

    async def append_frame(self, pcm_data: bytes, sample_rate: int, channels: int) -> None:
        """
        Append a raw audio frame. If resampling is needed, it happens here.
        For now, assume the input is already 24kHz mono.
        """
        # TODO: Implement actual resampling with numpy/scipy
        # For MVP, LiveKit can be configured to output 24kHz mono

        frame_size = len(pcm_data)
        if self._buffer_size + frame_size > self.MAX_BUFFER_SIZE:
            logger.warning("Audio buffer full, dropping oldest chunk")
            self._buffer_size -= len(self._buffer[0]) if self._buffer else 0
            if self._buffer:
                self._buffer.pop(0)

        self._buffer.append(pcm_data)
        self._buffer_size += frame_size

    async def drain(self) -> bytes:
        """Drain the accumulated audio buffer and return as bytes."""
        data = b"".join(self._buffer)
        self._buffer.clear()
        self._buffer_size = 0
        return data

    @property
    def buffer_size(self) -> int:
        return self._buffer_size


# ──── Silence detection (MTG-037) ────


class SilenceDetector:
    """
    Detects extended silence periods to avoid sending silent audio
    to the translation provider.
    """

    def __init__(self, silence_timeout_ms: int = 5000) -> None:
        self.silence_timeout_ms = silence_timeout_ms
        self._last_audio_time: float = 0.0
        self._silence_threshold: int = 100  # RMS threshold

    def update(self, pcm_data: bytes) -> None:
        """Update the last audio timestamp if sound is detected."""
        if self._has_signal(pcm_data):
            import time

            self._last_audio_time = time.monotonic() * 1000

    def is_silent(self) -> bool:
        """Return True if no audio signal has been detected recently."""
        import time

        now = time.monotonic() * 1000
        return (now - self._last_audio_time) > self.silence_timeout_ms

    def _has_signal(self, pcm_data: bytes) -> bool:
        """Simple RMS-based signal detection."""
        if len(pcm_data) < 2:
            return False
        import array

        samples = array.array("h", pcm_data)
        if len(samples) == 0:
            return False
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return rms > self._silence_threshold


# ──── Transcription provider interface (MTG-032) ────


class RealtimeTranscriptionProvider:
    """
    Interface for realtime transcription providers.

    Implementations:
    - OpenAIRealtimeTranscribeProvider (gpt-realtime-whisper)
    - OpenAIRealtimeTranslateProvider (gpt-realtime-translate)
    """

    async def start(self, language: str) -> None:
        """Open the WebSocket connection and configure the session."""
        raise NotImplementedError

    async def append_audio(self, pcm: bytes) -> None:
        """Send an audio chunk to the provider."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Close the connection and cleanup."""
        raise NotImplementedError

    async def receive(self) -> TranscriptionResult:
        """Wait for the next transcription delta or completion."""
        raise NotImplementedError


# ──── Translation provider interface (MTG-033) ────


class TranslationProvider:
    """
    Interface for text translation providers.

    The fallback provider (OpenAITranscribeThenTranslate) uses:
    1. RealtimeTranscriptionProvider for audio→text
    2. OpenAI text model for translation
    """

    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult:
        """Translate a partial (in-progress) utterance."""
        raise NotImplementedError

    async def translate_final(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        """Translate a completed utterance."""
        raise NotImplementedError


# ──── Participant pipeline (MTG-030) ────


@dataclass
class ParticipantAudioPipeline:
    """
    Manages the complete audio processing lifecycle for one participant:
    LiveKit track → audio normalization → OpenAI → translated captions.

    One instance per microphone track per participant.
    """

    participant_id: str
    participant_name: str
    spoken_language: str  # en | th
    caption_language: str  # en | th (the target translation language)

    _normalizer: AudioNormalizer = field(default_factory=AudioNormalizer)
    _silence_detector: SilenceDetector = field(default_factory=SilenceDetector)
    _transcription_provider: Optional[RealtimeTranscriptionProvider] = None
    _translation_provider: Optional[TranslationProvider] = None
    _state: PipelineState = PipelineState.IDLE
    _sequence: int = 0
    _revision: int = 0
    _caption_queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    async def start(self) -> None:
        """Initialize the OpenAI session for this participant."""
        self._state = PipelineState.STARTING
        logger.info(
            "Starting pipeline for %s (lang: %s→%s)",
            self.participant_name,
            self.spoken_language,
            self.caption_language,
        )
        # Provider would be injected based on env config
        self._state = PipelineState.RUNNING

    async def process_audio_frame(
        self,
        pcm_data: bytes,
        sample_rate: int,
        channels: int,
    ) -> None:
        """Process an incoming audio frame from LiveKit."""
        if self._state != PipelineState.RUNNING:
            return

        # Silence detection
        self._silence_detector.update(pcm_data)
        if self._silence_detector.is_silent():
            return

        # Normalize and buffer
        await self._normalizer.append_frame(pcm_data, sample_rate, channels)

    async def flush_captions(self) -> list[dict]:
        """Drain pending caption events from the queue."""
        captions = []
        while not self._caption_queue.empty():
            captions.append(await self._caption_queue.get())
        return captions

    async def stop(self) -> None:
        """Cleanup the pipeline for this participant."""
        self._state = PipelineState.STOPPING
        if self._transcription_provider:
            await self._transcription_provider.stop()
        self._state = PipelineState.IDLE
        logger.info("Stopped pipeline for %s", self.participant_name)

    @property
    def is_running(self) -> bool:
        return self._state == PipelineState.RUNNING
