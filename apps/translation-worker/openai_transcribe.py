"""
OpenAI realtime transcription provider (MTG-032).

Implements the RealtimeTranscriptionProvider interface using the
OpenAI Realtime Transcription API.

Current protocol:
- Session type: "transcription"
- Audio format: audio/pcm, rate 24000
- Model: gpt-realtime-whisper
- Audio buffer commits at speech boundaries, not every frame
"""

import asyncio
import base64
import json
import logging
import time
from typing import Optional

import websockets

from pipeline import RealtimeTranscriptionProvider, TranscriptionResult

logger = logging.getLogger("translation-worker.openai-transcribe")

MAX_RECONNECT_DELAY = 30.0
BASE_RECONNECT_DELAY = 1.0
COMMIT_INTERVAL_SECONDS = 0.5  # Commit audio every 500ms for reasonable turn sizes


class OpenAIRealtimeTranscribeProvider(RealtimeTranscriptionProvider):
    """
    Connects to OpenAI Realtime API for gpt-realtime-whisper transcription.

    Sends PCM16 24kHz mono audio chunks and receives transcription
    deltas and completion events. Commits audio at speech boundaries.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-realtime-whisper",
        base_url: str = "wss://api.openai.com/v1/realtime",
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._language: str = "en"
        self._connected: bool = False
        self._reconnect_attempts: int = 0
        self._event_queue: asyncio.Queue[TranscriptionResult] = asyncio.Queue()
        self._pending_items: dict[str, str] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._should_reconnect: bool = True
        self._last_commit_time: float = 0.0
        self._audio_buffered_since_commit: bool = False

    async def start(self, language: str) -> None:
        self._language = language
        self._should_reconnect = True
        await self._connect()

    async def stop(self) -> None:
        self._should_reconnect = False
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _connect(self) -> None:
        url = f"{self._base_url}?model={self._model}"

        while self._should_reconnect:
            try:
                self._ws = await websockets.connect(
                    url,
                    additional_headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "OpenAI-Beta": "realtime=v1",
                    },
                    ping_interval=20,
                    ping_timeout=10,
                )

                # Configure transcription session per current protocol
                await self._ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {
                            "input": {
                                "format": {
                                    "type": "audio/pcm",
                                    "rate": 24000,
                                },
                                "transcription": {
                                    "model": self._model,
                                    "language": self._language,
                                },
                            }
                        },
                    },
                }))

                self._connected = True
                self._reconnect_attempts = 0
                self._last_commit_time = time.monotonic()
                self._receive_task = asyncio.create_task(self._receive_loop())
                logger.info("Connected to OpenAI Realtime Transcription (model=%s, lang=%s)", self._model, self._language)
                return

            except websockets.InvalidStatus as e:
                logger.error("OpenAI permanent error: %s. Not retrying.", e)
                self._should_reconnect = False
                return
            except Exception as e:
                if not self._should_reconnect:
                    return
                self._reconnect_attempts += 1
                delay = min(BASE_RECONNECT_DELAY * (2 ** self._reconnect_attempts), MAX_RECONNECT_DELAY)
                logger.error("OpenAI connection failed (attempt %d): %s. Retrying in %.1fs", self._reconnect_attempts, e, delay)
                await asyncio.sleep(delay)

    async def append_audio(self, pcm: bytes) -> None:
        """Send audio chunk. Commits at intervals, not every frame."""
        if not self._ws or not self._connected:
            return

        try:
            encoded = base64.b64encode(pcm).decode("ascii")
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }))
            self._audio_buffered_since_commit = True

            # Commit at speech-turn boundaries, not every tiny frame
            now = time.monotonic()
            if now - self._last_commit_time >= COMMIT_INTERVAL_SECONDS:
                await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                self._last_commit_time = now
                self._audio_buffered_since_commit = False
        except Exception as e:
            logger.error("Failed to send audio: %s", e)
            self._connected = False

    async def receive(self) -> TranscriptionResult:
        return await self._event_queue.get()

    async def _receive_loop(self) -> None:
        try:
            async for message in self._ws:
                try:
                    event = json.loads(message)
                    await self._dispatch_event(event)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from OpenAI: %s", message[:100])
        except websockets.ConnectionClosed:
            logger.warning("OpenAI WebSocket closed")
            self._connected = False
            if self._should_reconnect:
                asyncio.create_task(self._connect())
        except Exception as e:
            logger.error("Receive loop error: %s", e)
            self._connected = False
            if self._should_reconnect:
                asyncio.create_task(self._connect())

    async def _dispatch_event(self, event: dict) -> None:
        event_type = event.get("type", "")
        if event_type == "conversation.item.input_audio_transcription.delta":
            await self._handle_transcription_delta(event)
        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self._handle_transcription_completed(event)
        elif event_type == "error":
            await self._handle_error(event)
        elif event_type == "session.created":
            logger.info("OpenAI session created: %s", event.get("session", {}).get("id"))

    async def _handle_transcription_delta(self, event: dict) -> None:
        item_id = event.get("item_id", "")
        delta = event.get("delta", "")
        if item_id not in self._pending_items:
            self._pending_items[item_id] = ""
        self._pending_items[item_id] += delta
        await self._event_queue.put(TranscriptionResult(
            text=self._pending_items[item_id], is_final=False,
            item_id=item_id, language=self._language,
        ))

    async def _handle_transcription_completed(self, event: dict) -> None:
        item_id = event.get("item_id", "")
        transcript = event.get("transcript", "")
        self._pending_items.pop(item_id, None)
        await self._event_queue.put(TranscriptionResult(
            text=transcript, is_final=True,
            item_id=item_id, language=self._language,
        ))

    async def _handle_error(self, event: dict) -> None:
        error = event.get("error", {})
        logger.error("OpenAI error [%s]: %s", error.get("code", "unknown"), error.get("message", "Unknown error"))
