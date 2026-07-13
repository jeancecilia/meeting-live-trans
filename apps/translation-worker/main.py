import asyncio
import logging
import os
import httpx
import json

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    WorkerType,
    cli,
    llm,
)
from livekit.plugins import openai
from livekit import rtc

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("translation-worker")

CAPTION_API_URL = os.environ.get("CAPTION_API_URL", "http://api:8000")
WORKER_SERVICE_TOKEN = os.environ.get("CAPTION_WORKER_SERVICE_TOKEN", "change-me")
API_URL = os.environ.get("API_URL", "http://api:8000")

async def get_meeting_id(room_name: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get(
                f"{API_URL}/api/internal/active-rooms",
                headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
            )
            if resp.status_code == 200:
                for r in resp.json():
                    if r["room_name"] == room_name:
                        return r["id"]
    except Exception as e:
        logger.error(f"Failed to fetch active rooms: {e}")
    return None

async def send_caption(meeting_id: str, event: dict) -> None:
    event["meeting_id"] = meeting_id
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            await c.post(
                f"{CAPTION_API_URL}/api/internal/meetings/{meeting_id}/caption-events",
                json=event,
                headers={"Authorization": f"Bearer {WORKER_SERVICE_TOKEN}"},
            )
    except Exception as e:
        logger.error("Failed to send caption: %s", e)

def get_language_from_participant(participant: rtc.RemoteParticipant) -> tuple[str, str]:
    """Parse participant metadata to determine their spoken and caption languages."""
    meta = participant.metadata
    spoken = "en"
    caption = "th"
    if meta:
        try:
            m = json.loads(meta)
            spoken = m.get("spoken_language", "en")
            # For simplicity, if they speak English, translate to Thai. If Thai, translate to English.
            caption = "th" if spoken == "en" else "en"
        except Exception:
            pass
    return spoken, caption

async def handle_participant_track(meeting_id: str, participant: rtc.RemoteParticipant, track: rtc.RemoteAudioTrack):
    logger.info(f"Setting up translation for {participant.identity}")
    
    spoken_lang, target_lang = get_language_from_participant(participant)
    
    instructions = (
        f"You are a highly skilled, lightning-fast translator. "
        f"You will receive audio of someone speaking {spoken_lang}. "
        f"Translate it directly into {target_lang}. "
        f"Output ONLY the translated text. Do not output conversational filler. "
        f"Do not output audio."
    )
    
    model = openai.realtime.RealtimeModel(
        model="gpt-realtime-mini",
        instructions=instructions,
        modalities=["text", "audio"],
    )
    session = model.session()


    audio_stream = rtc.AudioStream(track)

    seq = [0]
    current_text = [""]

    @session.on("response_text_delta")
    def on_text_delta(event):
        current_text[0] += event.delta
        asyncio.create_task(send_caption(meeting_id, {
            "type": "caption.delta",
            "speaker_id": participant.identity,
            "speaker_name": participant.name or participant.identity,
            "source_language": spoken_lang,
            "target_language": target_lang,
            "translated_text": current_text[0],
            "sequence": seq[0],
            "revision": 0,
            "is_final": False,
        }))

    @session.on("response_text_done")
    def on_text_done(event):
        asyncio.create_task(send_caption(meeting_id, {
            "type": "caption.final",
            "speaker_id": participant.identity,
            "speaker_name": participant.name or participant.identity,
            "source_language": spoken_lang,
            "target_language": target_lang,
            "translated_text": current_text[0],
            "sequence": seq[0],
            "revision": 1,
            "is_final": True,
        }))
        seq[0] += 1
        current_text[0] = ""

    @session.on("error")
    def on_error(event):
        logger.error(f"Realtime API error for {participant.identity}: {event}")

    async def pump_audio():
        try:
            async for event in audio_stream:
                session.push_audio(event.frame)
        except Exception as e:
            logger.error(f"Error processing audio for {participant.identity}: {e}")

    asyncio.create_task(pump_audio())

async def entrypoint(ctx: JobContext):
    logger.info(f"Starting agent for room {ctx.room.name}")
    meeting_id = await get_meeting_id(ctx.room.name)
    
    if not meeting_id:
        logger.error(f"Meeting ID not found for room {ctx.room.name}")
        return

    # Automatically subscribe to all audio tracks
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            asyncio.create_task(handle_participant_track(meeting_id, participant, track))

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
        )
    )
