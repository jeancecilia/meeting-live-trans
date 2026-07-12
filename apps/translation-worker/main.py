"""
Translation worker — polls API for active rooms, joins LiveKit hidden,
subscribes to mic tracks, processes audio through OpenAI pipeline.
"""

import asyncio
import logging
import os

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("translation-worker")

LIVEKIT_WS_URL = os.environ.get("LIVEKIT_WS_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")
CAPTION_API_URL = os.environ.get("CAPTION_API_URL", "http://api:8000")
WORKER_SERVICE_TOKEN = os.environ.get("CAPTION_WORKER_SERVICE_TOKEN", "change-me")
API_URL = os.environ.get("API_URL", "http://api:8000")
POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", "5"))

_active: dict[str, asyncio.Task] = {}


async def dispatch_rooms() -> None:
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                resp = await c.get(
                    f"{API_URL}/api/internal/active-rooms",
                    headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                )
                if resp.status_code == 200:
                    for r in resp.json():
                        rn = r["room_name"]
                        if rn not in _active:
                            logger.info("Dispatching worker: room=%s meeting=%s", rn, r["id"])
                            _active[rn] = asyncio.create_task(handle_room(r["id"], rn))
                done = [n for n, t in _active.items() if t.done()]
                for n in done:
                    del _active[n]
        except Exception as e:
            logger.error("Dispatch error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


def _parse_meta(s: str) -> dict:
    if not s:
        return {}
    d = {}
    for p in s.split(";"):
        p = p.strip()
        if ":" in p:
            k, v = p.split(":", 1)
            d[k.strip()] = v.strip()
    return d


async def handle_room(meeting_id: str, room_name: str) -> None:
    from livekit import api, rtc

    identity = f"worker_{room_name}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Translation Worker")
        .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=False, can_subscribe=True, hidden=True))
        .to_jwt()
    )

    room = rtc.Room()

    @room.on("track_subscribed")
    def on_track(track: rtc.Track, pub: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        logger.info("Audio track: %s/%s sid=%s", participant.name, participant.identity, track.sid)
        meta = _parse_meta(participant.metadata)
        sl = meta.get("spoken_language", "en")
        cl = "th" if sl == "en" else "en"
        stream = rtc.AudioStream(track, sample_rate=24000, num_channels=1)
        asyncio.create_task(process_audio(meeting_id, participant.identity, participant.name or participant.identity, sl, cl, stream))

    @room.on("participant_disconnected")
    def on_disconnect(participant: rtc.RemoteParticipant):
        logger.info("Participant left: %s", participant.identity)

    try:
        await room.connect(LIVEKIT_WS_URL, token)
        logger.info("Worker joined room: %s", room_name)
        while room.connection_state != rtc.ConnectionState.CONN_DISCONNECTED:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error("Room error %s: %s", room_name, e)
    finally:
        await room.disconnect()


async def process_audio(
    meeting_id: str, pid: str, pname: str,
    spoken_lang: str, caption_lang: str,
    audio_stream: "rtc.AudioStream",
) -> None:
    from pipeline import ParticipantAudioPipeline

    pipeline = ParticipantAudioPipeline(participant_id=pid, participant_name=pname, spoken_language=spoken_lang, caption_language=caption_lang)
    await pipeline.start()

    try:
        async for event in audio_stream:
            frame = event.frame
            await pipeline.process_audio_frame(frame.data.tobytes(), frame.sample_rate, frame.num_channels)

            for ev in await pipeline.flush_captions():
                ev["meeting_id"] = meeting_id
                async with httpx.AsyncClient(timeout=5.0) as c:
                    await c.post(
                        f"{CAPTION_API_URL}/api/internal/meetings/{meeting_id}/caption-events",
                        json=ev,
                        headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
                    )
    except Exception as e:
        logger.error("Audio error %s: %s", pname, e)
    finally:
        await pipeline.stop()


async def main() -> None:
    logger.info("Worker starting: LiveKit=%s API=%s", LIVEKIT_WS_URL, API_URL)
    await dispatch_rooms()


if __name__ == "__main__":
    asyncio.run(main())
