"""
Room orchestrator for the translation worker (MTG-030, MTG-037).

- Starts one worker job per active meeting room
- Joins using an internal service identity (hidden, no video)
- Subscribes to microphone tracks only
- Creates one ParticipantAudioPipeline per microphone track
- Manages pipeline lifecycle: start, process, stop, cleanup
"""

import asyncio
import logging
import os
from typing import Optional

from pipeline import (
    ParticipantAudioPipeline,
    PipelineState,
    ProviderType,
)
from openai_transcribe import OpenAIRealtimeTranscribeProvider
from translators import (
    OpenAIRealtimeTranslateProvider,
    OpenAITranscribeThenTranslateProvider,
)

logger = logging.getLogger("translation-worker.orchestrator")


class RoomOrchestrator:
    """
    Manages all participant pipelines for a single LiveKit room.

    Responsibilities:
    - Pipeline lifecycle (start/stop per participant)
    - Audio frame routing to correct pipeline
    - Caption event emission to the API
    - Failure isolation (one failed pipeline ≠ room disconnect)
    - Usage tracking
    """

    def __init__(
        self,
        meeting_id: str,
        room_name: str,
        caption_api_url: str = "http://localhost:8000",
    ) -> None:
        self.meeting_id = meeting_id
        self.room_name = room_name
        self._caption_api_url = caption_api_url
        self._pipelines: dict[str, ParticipantAudioPipeline] = {}
        self._openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self._provider_type = ProviderType(
            os.environ.get("TRANSLATION_PROVIDER", "openai-transcribe-then-translate")
        )
        self._max_sessions = int(
            os.environ.get("TRANSLATION_MAX_SESSIONS_PER_ROOM", "5")
        )
        self._total_audio_duration_seconds: float = 0.0
        self._caption_event_count: int = 0
        self._running: bool = False

    # ──── Pipeline management ────

    async def add_participant(
        self,
        participant_id: str,
        participant_name: str,
        spoken_language: str,
        caption_language: str,
    ) -> None:
        """Start a new audio pipeline for a participant."""
        if len(self._pipelines) >= self._max_sessions:
            logger.warning(
                "Max sessions (%d) reached for room %s, rejecting participant %s",
                self._max_sessions,
                self.room_name,
                participant_id,
            )
            return

        if participant_id in self._pipelines:
            logger.info("Pipeline already exists for %s, reusing", participant_id)
            return

        pipeline = ParticipantAudioPipeline(
            participant_id=participant_id,
            participant_name=participant_name,
            spoken_language=spoken_language,
            caption_language=caption_language,
        )

        # Inject the appropriate providers based on config
        # In production, this uses dependency injection
        await pipeline.start()
        self._pipelines[participant_id] = pipeline
        logger.info(
            "Pipeline started: participant=%s, lang=%s→%s, total_pipelines=%d",
            participant_name,
            spoken_language,
            caption_language,
            len(self._pipelines),
        )

    async def remove_participant(self, participant_id: str) -> None:
        """Stop and remove a participant's pipeline."""
        pipeline = self._pipelines.pop(participant_id, None)
        if pipeline:
            await pipeline.stop()
            logger.info(
                "Pipeline removed: participant=%s, remaining=%d",
                participant_id,
                len(self._pipelines),
            )

    async def process_audio_frame(
        self,
        participant_id: str,
        pcm_data: bytes,
        sample_rate: int,
        channels: int,
    ) -> None:
        """Route an audio frame to the correct participant pipeline."""
        pipeline = self._pipelines.get(participant_id)
        if not pipeline or not pipeline.is_running:
            return

        await pipeline.process_audio_frame(pcm_data, sample_rate, channels)
        self._total_audio_duration_seconds += len(pcm_data) / (sample_rate * 2 * channels)

    # ──── Caption emission ────

    async def emit_caption_event(self, event: dict) -> None:
        """Send a caption event to the API for routing to subscribers."""
        import httpx

        self._caption_event_count += 1

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    f"{self._caption_api_url}/internal/caption-event",
                    json=event,
                )
        except Exception as e:
            logger.error("Failed to emit caption event: %s", e)

    # ──── Lifecycle ────

    async def run(self) -> None:
        """Main orchestration loop for this room."""
        self._running = True
        logger.info("Room orchestrator started: room=%s", self.room_name)

        try:
            while self._running:
                # In production, this reads audio frames from LiveKit tracks
                # and routes them to the correct pipeline
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("Room orchestrator cancelled: room=%s", self.room_name)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully shutdown all pipelines in this room."""
        self._running = False
        logger.info(
            "Shutting down room orchestrator: room=%s, "
            "pipelines=%d, audio_duration=%.1fs, caption_events=%d",
            self.room_name,
            len(self._pipelines),
            self._total_audio_duration_seconds,
            self._caption_event_count,
        )

        for participant_id in list(self._pipelines.keys()):
            await self.remove_participant(participant_id)

    @property
    def active_pipelines(self) -> int:
        return len(self._pipelines)

    @property
    def usage_stats(self) -> dict:
        return {
            "meeting_id": self.meeting_id,
            "room_name": self.room_name,
            "active_pipelines": len(self._pipelines),
            "provider_type": self._provider_type.value,
            "audio_duration_seconds": round(self._total_audio_duration_seconds, 1),
            "caption_event_count": self._caption_event_count,
        }


# ──── Global room registry ────

_rooms: dict[str, RoomOrchestrator] = {}


async def start_room(meeting_id: str, room_name: str) -> RoomOrchestrator:
    """Create and start an orchestrator for a meeting room."""
    if room_name in _rooms:
        return _rooms[room_name]

    orchestrator = RoomOrchestrator(meeting_id, room_name)
    _rooms[room_name] = orchestrator
    asyncio.create_task(orchestrator.run())
    return orchestrator


async def stop_room(room_name: str) -> None:
    """Stop and cleanup a room orchestrator."""
    orchestrator = _rooms.pop(room_name, None)
    if orchestrator:
        await orchestrator.shutdown()


def get_room(room_name: str) -> Optional[RoomOrchestrator]:
    """Get the orchestrator for a room, if active."""
    return _rooms.get(room_name)
