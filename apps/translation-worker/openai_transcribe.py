"""
OpenAI realtime transcription provider.

Commits audio at utterance boundaries (silence-based), not on a fixed timer.
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
SILENCE_COMMIT_MS = 500   # Commit after this much silence


class OpenAIRealtimeTranscribeProvider(RealtimeTranscriptionProvider):
    def __init__(self, api_key: str, model: str = "gpt-realtime-whisper", base_url: str = "wss://api.openai.com/v1/realtime") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._language: str = "en"
        self._connected: bool = False
        self._attempts: int = 0
        self._queue: asyncio.Queue[TranscriptionResult] = asyncio.Queue()
        self._pending: dict[str, str] = {}
        self._task: Optional[asyncio.Task] = None
        self._reconnect: bool = True
        # Silence-based commit tracking
        self._last_signal_time: float = 0.0
        self._committed: bool = True

    async def start(self, language: str) -> None:
        self._language = language
        self._reconnect = True
        await self._connect()

    async def stop(self) -> None:
        self._reconnect = False
        self._connected = False
        if self._task:
            self._task.cancel()
            self._task = None
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _connect(self) -> None:
        url = f"{self._base_url}?model={self._model}"
        while self._reconnect:
            try:
                self._ws = await websockets.connect(url, additional_headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "OpenAI-Beta": "realtime=v1",
                }, ping_interval=20, ping_timeout=10)

                await self._ws.send(json.dumps({"type": "session.update", "session": {
                    "type": "transcription",
                    "audio": {"input": {"format": {"type": "audio/pcm", "rate": 24000}, "transcription": {"model": self._model, "language": self._language}}},
                }}))

                self._connected = True
                self._attempts = 0
                self._last_signal_time = time.monotonic()
                self._task = asyncio.create_task(self._receive_loop())
                logger.info("OpenAI connected (model=%s lang=%s)", self._model, self._language)
                return
            except websockets.InvalidStatus as e:
                logger.error("Permanent error: %s", e)
                self._reconnect = False
                return
            except Exception as e:
                if not self._reconnect:
                    return
                self._attempts += 1
                delay = min(BASE_RECONNECT_DELAY * (2 ** self._attempts), MAX_RECONNECT_DELAY)
                logger.error("Connect failed (%d): %s. Retry in %.1fs", self._attempts, e, delay)
                await asyncio.sleep(delay)

    async def append_audio(self, pcm: bytes) -> None:
        if not self._ws or not self._connected:
            return
        try:
            encoded = base64.b64encode(pcm).decode("ascii")
            await self._ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": encoded}))

            # Detect if this chunk contains actual speech signal
            has_signal = self._has_signal(pcm)
            now = time.monotonic()

            if has_signal:
                self._last_signal_time = now
                self._committed = False
            elif not self._committed and (now - self._last_signal_time) * 1000 >= SILENCE_COMMIT_MS:
                # Sustained silence after speech → commit the utterance
                await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                self._committed = True
                logger.debug("Utterance committed after silence")
        except Exception as e:
            logger.error("Audio send failed: %s", e)
            self._connected = False

    def _has_signal(self, pcm: bytes) -> bool:
        if len(pcm) < 2:
            return False
        import array
        samples = array.array("h", pcm)
        if len(samples) == 0:
            return False
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return rms > 100

    async def receive(self) -> TranscriptionResult:
        return await self._queue.get()

    async def _receive_loop(self) -> None:
        try:
            async for message in self._ws:
                try:
                    ev = json.loads(message)
                    await self._dispatch(ev)
                except json.JSONDecodeError:
                    logger.warning("Bad JSON: %s", message[:100])
        except websockets.ConnectionClosed:
            logger.warning("WS closed")
            self._connected = False
            if self._reconnect:
                asyncio.create_task(self._connect())
        except Exception as e:
            logger.error("Recv error: %s", e)
            self._connected = False
            if self._reconnect:
                asyncio.create_task(self._connect())

    async def _dispatch(self, ev: dict) -> None:
        t = ev.get("type", "")
        if t == "conversation.item.input_audio_transcription.delta":
            iid = ev.get("item_id", "")
            self._pending[iid] = self._pending.get(iid, "") + ev.get("delta", "")
            await self._queue.put(TranscriptionResult(text=self._pending[iid], is_final=False, item_id=iid, language=self._language))
        elif t == "conversation.item.input_audio_transcription.completed":
            iid = ev.get("item_id", "")
            self._pending.pop(iid, None)
            await self._queue.put(TranscriptionResult(text=ev.get("transcript", ""), is_final=True, item_id=iid, language=self._language))
        elif t == "error":
            logger.error("OpenAI error: %s", ev.get("error", {}).get("message", "Unknown"))
        elif t == "session.created":
            logger.info("Session created: %s", ev.get("session", {}).get("id"))
