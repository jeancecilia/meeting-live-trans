"""LiveKit room worker for private English/Thai translated captions.

Each microphone track gets an independent transcription and translation
pipeline. Caption events are delivered to the FastAPI caption router; raw
audio and spoken content are never logged or stored by this worker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, WorkerType, cli

from pipeline import ParticipantAudioPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("translation-worker")

CAPTION_API_URL = os.environ.get("CAPTION_API_URL", "http://api:8000").rstrip("/")
WORKER_SERVICE_TOKEN = os.environ.get(
    "CAPTION_WORKER_SERVICE_TOKEN", "change-me"
)
API_URL = os.environ.get("API_URL", "http://api:8000").rstrip("/")
MEETING_LOOKUP_ATTEMPTS = int(os.environ.get("MEETING_LOOKUP_ATTEMPTS", "10"))


async def get_meeting_id(room_name: str) -> str | None:
    """Resolve the application meeting ID for a LiveKit room."""
    for attempt in range(1, MEETING_LOOKUP_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{API_URL}/api/internal/active-rooms",
                    headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                )
                response.raise_for_status()
                for room in response.json():
                    if room["room_name"] == room_name:
                        return str(room["id"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "Meeting lookup failed: room=%s attempt=%d/%d error=%s",
                room_name,
                attempt,
                MEETING_LOOKUP_ATTEMPTS,
                type(exc).__name__,
            )

        if attempt < MEETING_LOOKUP_ATTEMPTS:
            await asyncio.sleep(min(attempt, 3))

    return None


async def send_caption_event(meeting_id: str, event: dict[str, Any]) -> None:
    """Send one validated caption or system event to the API."""
    payload = {**event, "meeting_id": meeting_id}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{CAPTION_API_URL}/api/internal/meetings/{meeting_id}/caption-events",
                json=payload,
                headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Caption API rejected event: meeting=%s type=%s status=%d",
            meeting_id,
            event.get("type", "unknown"),
            exc.response.status_code,
        )
        raise
    except httpx.HTTPError:
        logger.exception(
            "Caption API request failed: meeting=%s type=%s",
            meeting_id,
            event.get("type", "unknown"),
        )
        raise


def parse_participant_metadata(metadata: str | None) -> dict[str, str]:
    """Parse JSON metadata and support legacy semicolon-delimited tokens."""
    if not metadata:
        return {}

    try:
        parsed = json.loads(metadata)
        if isinstance(parsed, dict):
            return {str(key): str(value) for key, value in parsed.items()}
    except (json.JSONDecodeError, TypeError):
        pass

    parsed_legacy: dict[str, str] = {}
    for item in metadata.split(";"):
        key, separator, value = item.strip().partition(":")
        if separator and key:
            parsed_legacy[key.strip()] = value.strip()
    return parsed_legacy


def participant_languages(participant: rtc.RemoteParticipant) -> tuple[str, str]:
    """Return a supported source language and its opposite caption language."""
    metadata = parse_participant_metadata(participant.metadata)
    spoken_language = metadata.get("spoken_language", "en").lower()
    if spoken_language not in {"en", "th"}:
        logger.warning(
            "Unsupported participant language; defaulting to en: participant=%s",
            participant.identity,
        )
        spoken_language = "en"
    target_language = "th" if spoken_language == "en" else "en"
    return spoken_language, target_language


def _track_is_microphone(
    track: rtc.Track, publication: rtc.TrackPublication
) -> bool:
    return (
        track.kind == rtc.TrackKind.KIND_AUDIO
        and publication.source == rtc.TrackSource.SOURCE_MICROPHONE
    )


async def process_microphone_track(
    meeting_id: str,
    participant: rtc.RemoteParticipant,
    track: rtc.RemoteAudioTrack,
) -> None:
    """Run a participant microphone track until it is unpublished."""
    source_language, target_language = participant_languages(participant)
    participant_name = participant.name or participant.identity

    logger.info(
        "Starting audio pipeline: meeting=%s participant=%s source=%s target=%s",
        meeting_id,
        participant.identity,
        source_language,
        target_language,
    )

    async def caption_sink(event: dict[str, Any]) -> None:
        await send_caption_event(meeting_id, event)

    async def error_sink(message: str) -> None:
        await send_caption_event(
            meeting_id,
            {
                "type": "system.error",
                "speaker_id": "system",
                "speaker_name": "Translation service",
                "message": message,
            },
        )

    pipeline = ParticipantAudioPipeline(
        participant_id=participant.identity,
        participant_name=participant_name,
        spoken_language=source_language,
        caption_language=target_language,
        caption_sink=caption_sink,
        error_sink=error_sink,
    )
    audio_stream = rtc.AudioStream(track, sample_rate=24_000, num_channels=1)

    try:
        await pipeline.start()
        async for audio_event in audio_stream:
            frame = audio_event.frame
            await pipeline.process_audio_frame(
                frame.data.tobytes(), frame.sample_rate, frame.num_channels
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "Audio pipeline failed: meeting=%s participant=%s",
            meeting_id,
            participant.identity,
        )
        try:
            await error_sink("Translation is temporarily unavailable.")
        except Exception:
            logger.exception("Failed to publish translation error event")
    finally:
        try:
            await pipeline.finish()
        except Exception:
            logger.exception(
                "Failed to stop audio pipeline: meeting=%s participant=%s",
                meeting_id,
                participant.identity,
            )
        finally:
            await audio_stream.aclose()
        logger.info(
            "Stopped audio pipeline: meeting=%s participant=%s",
            meeting_id,
            participant.identity,
        )


async def entrypoint(ctx: JobContext) -> None:
    """Join a dispatched room and subscribe to microphone tracks."""
    # The RTC room is not connected yet, so use the dispatched job metadata.
    room_name = ctx.job.room.name
    logger.info("Starting room worker: room=%s", room_name)

    meeting_id = await get_meeting_id(room_name)
    if not meeting_id:
        logger.error("Meeting ID not found: room=%s", room_name)
        ctx.shutdown(reason="meeting not found")
        return

    track_tasks: dict[str, asyncio.Task[None]] = {}

    def start_track(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if not _track_is_microphone(track, publication):
            return
        if publication.sid in track_tasks and not track_tasks[publication.sid].done():
            return

        task = asyncio.create_task(
            process_microphone_track(meeting_id, participant, track),
            name=f"translate-{participant.identity}-{publication.sid}",
        )
        track_tasks[publication.sid] = task

        def task_done(completed: asyncio.Task[None]) -> None:
            track_tasks.pop(publication.sid, None)
            if not completed.cancelled() and completed.exception() is not None:
                logger.error(
                    "Track task exited with an error: participant=%s track=%s",
                    participant.identity,
                    publication.sid,
                    exc_info=completed.exception(),
                )

        task.add_done_callback(task_done)

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.TrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        start_track(track, publication, participant)

    @ctx.room.on("track_unsubscribed")
    def on_track_unsubscribed(
        _track: rtc.Track,
        publication: rtc.TrackPublication,
        _participant: rtc.RemoteParticipant,
    ) -> None:
        if task := track_tasks.get(publication.sid):
            task.cancel()

    async def shutdown_tracks() -> None:
        tasks = list(track_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    ctx.add_shutdown_callback(shutdown_tracks)

    # Register handlers before connecting so tracks published by the first
    # participant cannot be missed during the initial room synchronization.
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Also process any tracks already synchronized before subscriptions fired.
    for participant in ctx.room.remote_participants.values():
        for publication in participant.track_publications.values():
            track = publication.track
            if track is not None:
                start_track(track, publication, participant)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
        )
    )
