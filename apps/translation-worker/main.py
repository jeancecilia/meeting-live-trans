"""
Translation worker entry point (MTG-030).

Polls the API for active meeting rooms, joins LiveKit rooms as a hidden
service participant, processes individual microphone tracks, and routes
translated captions to the FastAPI caption ingest endpoint.
"""

import asyncio
import json
import logging
import os

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("translation-worker")

LIVEKIT_WS_URL = os.environ.get("LIVEKIT_WS_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
CAPTION_API_URL = os.environ.get("CAPTION_API_URL", "http://api:8000")
WORKER_SERVICE_TOKEN = os.environ.get("CAPTION_WORKER_SERVICE_TOKEN", "change-me")
API_URL = os.environ.get("API_URL", "http://api:8000")
POLL_INTERVAL_SECONDS = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))

_active_room_tasks: dict[str, asyncio.Task] = {}


async def dispatch_rooms() -> None:
    """Poll the API for active rooms and dispatch worker tasks."""
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{API_URL}/api/internal/active-rooms",
                    headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                )
                if resp.status_code == 200:
                    rooms = resp.json()
                    for room in rooms:
                        room_name = room["room_name"]
                        meeting_id = room["id"]
                        if room_name not in _active_room_tasks:
                            logger.info("Dispatching worker to room: %s (meeting=%s)", room_name, meeting_id)
                            task = asyncio.create_task(handle_room(meeting_id, room_name))
                            _active_room_tasks[room_name] = task

                finished = [n for n, t in _active_room_tasks.items() if t.done()]
                for name in finished:
                    del _active_room_tasks[name]
        except Exception as e:
            logger.error("Room dispatch error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _parse_participant_metadata(metadata_str: str) -> dict:
    """Parse LiveKit participant metadata string into dict."""
    if not metadata_str:
        return {}
    result = {}
    for pair in metadata_str.split(";"):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            result[k.strip()] = v.strip()
    return result


async def handle_room(meeting_id: str, room_name: str) -> None:
    """Join a LiveKit room as a hidden worker and process participant audio tracks."""
    from livekit import api, rtc

    identity = f"worker_{room_name}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Translation Worker")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=False,
                can_subscribe=True,
            )
        )
        .to_jwt()
    )

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        logger.info("Audio track: participant=%s identity=%s track_sid=%s", participant.name, participant.identity, track.sid)

        # Read participant metadata for language direction
        meta = _parse_participant_metadata(participant.metadata)
        spoken_language = meta.get("spoken_language", "en")
        caption_language = "th" if spoken_language == "en" else "en"

        # Create audio stream at the correct sample rate
        audio_stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)

        asyncio.create_task(process_audio_stream(
            meeting_id=meeting_id,
            participant_identity=participant.identity,
            participant_name=participant.name or participant.identity,
            spoken_language=spoken_language,
            caption_language=caption_language,
            audio_stream=audio_stream,
        ))

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info("Participant disconnected: %s", participant.identity)

    try:
        await room.connect(LIVEKIT_WS_URL, token)
        logger.info("Worker joined room: %s (meeting=%s)", room_name, meeting_id)

        while room.connection_state != rtc.ConnectionState.CONN_DISCONNECTED:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error("Room connection error for %s: %s", room_name, e)
    finally:
        await room.disconnect()
        logger.info("Worker left room: %s", room_name)


async def process_audio_stream(
    meeting_id: str,
    participant_identity: str,
    participant_name: str,
    spoken_language: str,
    caption_language: str,
    audio_stream: "rtc.AudioStream",
) -> None:
    """Process audio frames through the full translation pipeline."""
    from pipeline import ParticipantAudioPipeline

    pipeline = ParticipantAudioPipeline(
        participant_id=participant_identity,
        participant_name=participant_name,
        spoken_language=spoken_language,
        caption_language=caption_language,
    )
    await pipeline.start()

    try:
        async for event in audio_stream:
            frame = event.frame
            pcm_data = frame.data.tobytes()
            sample_rate = frame.sample_rate
            channels = frame.num_channels

            await pipeline.process_audio_frame(pcm_data, sample_rate, channels)

            # Emit all pending captions
            caption_events = await pipeline.flush_captions()
            for caption_event in caption_events:
                caption_event["meeting_id"] = meeting_id
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{CAPTION_API_URL}/api/internal/meetings/{meeting_id}/caption-events",
                        json=caption_event,
                        headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                    )
    except Exception as e:
        logger.error("Audio processing error for %s: %s", participant_name, e)
    finally:
        await pipeline.stop()


async def main() -> None:
    logger.info("Translation worker starting...")
    logger.info("LiveKit WS: %s, API: %s", LIVEKIT_WS_URL, API_URL)
    await dispatch_rooms()


if __name__ == "__main__":
    asyncio.run(main())
