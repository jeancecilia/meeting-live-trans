"""
Translation worker entry point (MTG-030).

Subscribes to Redis for room dispatch, joins LiveKit rooms as a hidden
service participant, processes individual microphone tracks, and routes
translated captions to the FastAPI caption ingest endpoint.
"""

import asyncio
import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("translation-worker")

LIVEKIT_HOST = os.environ.get("LIVEKIT_HOST", "localhost")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
CAPTION_API_URL = os.environ.get("CAPTION_API_URL", "http://localhost:8000")
WORKER_SERVICE_TOKEN = os.environ.get("CAPTION_WORKER_SERVICE_TOKEN", "change-me")


async def handle_room(meeting_id: str, room_name: str) -> None:
    """
    Join a LiveKit room as a hidden worker and process participant audio tracks.

    Uses the LiveKit Python SDK to:
    1. Connect to the room with a service identity
    2. Subscribe to all microphone tracks
    3. Process audio through the translation pipeline
    4. Send captions to the API ingest endpoint
    """
    from livekit import rtc

    identity = f"worker_{room_name}"
    token = (
        rtc.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Translation Worker")
        .with_grants(rtc.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=False,
            can_subscribe=True,
        ))
        .to_jwt()
    )

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return

        logger.info(
            "Subscribed to audio track: participant=%s identity=%s track_sid=%s",
            participant.name,
            participant.identity,
            track.sid,
        )

        # Create audio stream and process frames
        audio_stream = rtc.AudioStream(track)
        asyncio.create_task(process_audio_stream(
            meeting_id=meeting_id,
            participant_identity=participant.identity,
            participant_name=participant.name or participant.identity,
            audio_stream=audio_stream,
        ))

    @room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info("Participant disconnected: %s", participant.identity)

    try:
        await room.connect(LIVEKIT_HOST, token)
        logger.info("Worker joined room: %s (meeting=%s)", room_name, meeting_id)

        # Keep running until room disconnects
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
    audio_stream: "rtc.AudioStream",
) -> None:
    """
    Process audio frames from a participant's microphone track.

    Pipeline: LiveKit frame → normalize → OpenAI → translate → caption API
    """
    from pipeline import ParticipantAudioPipeline
    import httpx

    # Determine languages from participant identity metadata
    # In production, this reads from the LiveKit participant attributes
    spoken_language = "en"
    caption_language = "th"

    pipeline = ParticipantAudioPipeline(
        participant_id=participant_identity,
        participant_name=participant_name,
        spoken_language=spoken_language,
        caption_language=caption_language,
    )
    await pipeline.start()

    try:
        async for frame in audio_stream:
            # frame.data contains PCM16 audio bytes
            pcm_data = bytes(frame.data) if hasattr(frame.data, "tobytes") else frame.data
            sample_rate = getattr(frame, "sample_rate", 24000)
            channels = getattr(frame, "num_channels", 1)

            await pipeline.process_audio_frame(pcm_data, sample_rate, channels)

            # Emit buffered captions
            caption_events = await pipeline.flush_captions()
            for event in caption_events:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    await client.post(
                        f"{CAPTION_API_URL}/api/internal/meetings/{meeting_id}/caption-events",
                        json=event,
                        headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                    )
    except Exception as e:
        logger.error("Audio processing error for %s: %s", participant_name, e)
    finally:
        await pipeline.stop()


async def main() -> None:
    logger.info("Translation worker starting...")
    logger.info("LiveKit host: %s", LIVEKIT_HOST)

    # In production: subscribe to Redis pub/sub for room dispatch events
    # For MVP: poll the API for active rooms or accept room assignments
    try:
        while True:
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        logger.info("Worker shutting down...")
    except KeyboardInterrupt:
        logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
