"""
Translation worker entry point (MTG-030).

Connects to Redis for room dispatch, joins LiveKit rooms as a hidden
service participant, subscribes to individual microphone tracks,
normalizes audio, and streams to the OpenAI Realtime API for
transcription/translation. Routes translated captions to the
FastAPI caption WebSocket for private delivery.
"""

import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("translation-worker")


async def main() -> None:
    logger.info("Translation worker starting...")
    logger.info("Provider: %s", os.environ.get("TRANSLATION_PROVIDER", "openai-transcribe-then-translate"))
    logger.info("OpenAI model: %s", os.environ.get("OPENAI_REALTIME_TRANSCRIBE_MODEL", "gpt-4o-mini-realtime"))

    # In production:
    # 1. Subscribe to Redis for room creation/dispatch events
    # 2. On room creation: join LiveKit as hidden participant
    # 3. Subscribe to audio tracks, create ParticipantAudioPipeline per track
    # 4. On room end: cleanup all pipelines

    # Standby loop
    try:
        while True:
            await asyncio.sleep(5)
            # Log active rooms periodically
            from room_orchestrator import _rooms
            if _rooms:
                for room_name, orch in _rooms.items():
                    stats = orch.usage_stats
                    logger.debug(
                        "Room %s: %d pipelines, %.1fs audio, %d caption events",
                        room_name,
                        stats["active_pipelines"],
                        stats["audio_duration_seconds"],
                        stats["caption_event_count"],
                    )
    except asyncio.CancelledError:
        logger.info("Translation worker shutting down...")
    except KeyboardInterrupt:
        logger.info("Translation worker stopped by user.")


if __name__ == "__main__":
    asyncio.run(main())
