"""
OpenAI realtime transcription provider (MTG-032).

Implements the RealtimeTranscriptionProvider interface using the
OpenAI Realtime WebSocket API for gpt-realtime-whisper.

Handles:
- conversation.item.input_audio_transcription.delta
- conversation.item.input_audio_transcription.completed
- error
- connection closed
"""

import asyncio
import json
import logging
import time
from typing import Optional

import websockets

from pipeline import RealtimeTranscriptionProvider, TranscriptionResult

logger = logging.getLogger("translation-worker.openai-transcribe")

# Reconnect configuration (bounded exponential backoff)
MAX_RECONNECT_DELAY = 30.0
BASE_RECONNECT_DELAY = 1.0


class OpenAIRealtimeTranscribeProvider(RealtimeTranscriptionProvider):
    """
    Connects to OpenAI Realtime API for gpt-realtime-whisper transcription.

    Sends PCM16 24kHz mono audio chunks and receives transcription
    deltas and completion events.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-realtime",
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
        self._pending_items: dict[str, str] = {}  # item_id → partial text
        self._receive_task: Optional[asyncio.Task] = None

    # ──── Connection management ────

    async def start(self, language: str) -> None:
        """Open WebSocket and initialize the transcription session."""
        self._language = language
        await self._connect()

    async def stop(self) -> None:
        """Close the WebSocket and cleanup."""
        self._connected = False
        if self._receive_task:
            self._receive_task.cancel()
            self._receive_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _connect(self) -> None:
        """Establish WebSocket connection with bounded exponential backoff."""
        url = f"{self._base_url}?model={self._model}"

        while True:
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

                # Configure the session for transcription
                await self._ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "input_audio_transcription": {
                            "model": "whisper-1",
                            "language": self._language,
                        },
                    },
                }))

                self._connected = True
                self._reconnect_attempts = 0
                self._receive_task = asyncio.create_task(self._receive_loop())
                logger.info("Connected to OpenAI Realtime (transcribe, lang=%s)", self._language)
                return

            except Exception as e:
                self._reconnect_attempts += 1
                delay = min(BASE_RECONNECT_DELAY * (2 ** self._reconnect_attempts), MAX_RECONNECT_DELAY)
                logger.error(
                    "OpenAI connection failed (attempt %d): %s. Retrying in %.1fs",
                    self._reconnect_attempts,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

    # ──── Audio input ────

    async def append_audio(self, pcm: bytes) -> None:
        """Send an audio buffer chunk to OpenAI."""
        if not self._ws or not self._connected:
            return

        try:
            # OpenAI Realtime API expects base64-encoded PCM16
            import base64

            encoded = base64.b64encode(pcm).decode("ascii")
            await self._ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }))
        except Exception as e:
            logger.error("Failed to send audio: %s", e)
            self._connected = False

    # ──── Event receiving ────

    async def receive(self) -> TranscriptionResult:
        """Get the next transcription event from the queue."""
        return await self._event_queue.get()

    async def _receive_loop(self) -> None:
        """Continuously receive and dispatch events from the WebSocket."""
        try:
            async for message in self._ws:
                try:
                    event = json.loads(message)
                    await self._dispatch_event(event)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from OpenAI: %s", message[:100])
                except Exception as e:
                    logger.error("Error dispatching event: %s", e)
        except websockets.ConnectionClosed:
            logger.warning("OpenAI WebSocket closed")
            self._connected = False
        except Exception as e:
            logger.error("Receive loop error: %s", e)
            self._connected = False

    async def _dispatch_event(self, event: dict) -> None:
        """Route incoming events by type."""
        event_type = event.get("type", "")

        if event_type == "conversation.item.input_audio_transcription.delta":
            await self._handle_transcription_delta(event)
        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self._handle_transcription_completed(event)
        elif event_type == "error":
            await self._handle_error(event)
        elif event_type == "session.created":
            logger.info("OpenAI session created: %s", event.get("session", {}).get("id"))
        elif event_type == "session.updated":
            logger.info("OpenAI session updated")

    async def _handle_transcription_delta(self, event: dict) -> None:
        """Handle a partial transcription delta."""
        item_id = event.get("item_id", "")
        delta = event.get("delta", "")

        if item_id not in self._pending_items:
            self._pending_items[item_id] = ""
        self._pending_items[item_id] += delta

        result = TranscriptionResult(
            text=self._pending_items[item_id],
            is_final=False,
            item_id=item_id,
            language=self._language,
        )
        await self._event_queue.put(result)

    async def _handle_transcription_completed(self, event: dict) -> None:
        """Handle a completed transcription."""
        item_id = event.get("item_id", "")
        transcript = event.get("transcript", "")

        # Use the completed transcript, which may differ from accumulated deltas
        self._pending_items.pop(item_id, None)

        result = TranscriptionResult(
            text=transcript,
            is_final=True,
            item_id=item_id,
            language=self._language,
        )
        await self._event_queue.put(result)

    async def _handle_error(self, event: dict) -> None:
        """Handle OpenAI errors without crashing the pipeline."""
        error = event.get("error", {})
        logger.error(
            "OpenAI error [%s]: %s",
            error.get("code", "unknown"),
            error.get("message", "Unknown error"),
        )
