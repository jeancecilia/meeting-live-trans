"""OpenAI Realtime transcription-only WebSocket provider."""

from __future__ import annotations

import array
import asyncio
import base64
import json
import logging
import os
import time
from typing import Any

import websockets

from pipeline import TranscriptionResult

logger = logging.getLogger("translation-worker.openai-transcribe")

PCM_BYTES_PER_SECOND = 24_000 * 2
MIN_COMMIT_BYTES = PCM_BYTES_PER_SECOND // 10


class OpenAIRealtimeTranscribeProvider:
    """Stream mono PCM16 audio and expose partial/final transcript events."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-realtime-mini",
        base_url: str | None = None,
        max_connect_attempts: int = 3,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (
            base_url
            or os.environ.get("OPENAI_REALTIME_URL")
            or "wss://api.openai.com/v1/realtime"
        )
        self._max_connect_attempts = max_connect_attempts
        self._language = "en"
        self._websocket: Any | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._results: asyncio.Queue[TranscriptionResult | Exception] = asyncio.Queue()
        self._partials: dict[str, str] = {}
        self._connected = False
        self._stopping = False
        self._last_signal_time = 0.0
        self._buffered_bytes = 0
        self._commit_lock = asyncio.Lock()
        self._reconnect_lock = asyncio.Lock()
        self._silence_commit_ms = int(
            os.environ.get("OPENAI_TRANSCRIPTION_SILENCE_COMMIT_MS", "500")
        )

    async def start(self, language: str) -> None:
        if not self._api_key or self._api_key == "sk-change-me":
            raise RuntimeError("OPENAI_API_KEY is not configured")
        if language not in {"en", "th"}:
            raise ValueError(f"Unsupported transcription language: {language}")

        self._language = language
        self._stopping = False
        await self._connect()

    async def _connect(self) -> None:
        url = f"{self._base_url}?model={self._model}"
        last_error: Exception | None = None

        for attempt in range(1, self._max_connect_attempts + 1):
            try:
                self._websocket = await websockets.connect(
                    url,
                    additional_headers={
                        "Authorization": f"Bearer {self._api_key}"
                    },
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=2**20,
                )
                await self._websocket.send(
                    json.dumps(
                        {
                            "type": "session.update",
                            "session": {
                                "type": "realtime",
                                "audio": {
                                    "input": {
                                        "format": {
                                            "type": "audio/pcm",
                                            "rate": 24_000,
                                        },
                                        "transcription": {
                                            "model": "whisper-1",
                                            "language": self._language,
                                        },
                                        "turn_detection": None,
                                    }
                                }
                            }
                        }
                    )
                )
                self._connected = True
                self._receive_task = asyncio.create_task(
                    self._receive_loop(), name="openai-transcription-receive"
                )
                logger.info(
                    "OpenAI transcription connected: model=%s language=%s",
                    self._model,
                    self._language,
                )
                return
            except Exception as exc:
                last_error = exc
                self._connected = False
                logger.warning(
                    "OpenAI transcription connection failed: attempt=%d/%d error=%s",
                    attempt,
                    self._max_connect_attempts,
                    type(exc).__name__,
                )
                if attempt < self._max_connect_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))

        raise RuntimeError("Unable to connect to OpenAI Realtime transcription") from last_error

    async def append_audio(self, pcm: bytes) -> None:
        if not pcm:
            return

        has_signal = self._has_signal(pcm)
        if not has_signal and self._last_signal_time == 0 and self._buffered_bytes == 0:
            return

        if not self._connected or self._websocket is None:
            async with self._reconnect_lock:
                if not self._connected or self._websocket is None:
                    await self._connect()

        try:
            await self._websocket.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm).decode("ascii"),
                    }
                )
            )
            self._buffered_bytes += len(pcm)

            now = time.monotonic()
            if has_signal:
                self._last_signal_time = now
            elif (
                self._last_signal_time > 0
                and (now - self._last_signal_time) * 1_000
                >= self._silence_commit_ms
            ):
                await self._commit_now()
        except Exception:
            self._connected = False
            logger.exception("Failed to append audio to OpenAI")
            raise

    async def commit_pending(self) -> bool:
        return await self._commit_now()

    async def _commit_now(self) -> bool:
        async with self._commit_lock:
            if (
                not self._connected
                or self._websocket is None
                or self._buffered_bytes < MIN_COMMIT_BYTES
            ):
                return False
            await self._websocket.send(
                json.dumps({"type": "input_audio_buffer.commit"})
            )
            self._buffered_bytes = 0
            self._last_signal_time = 0.0
            return True

    def _has_signal(self, pcm: bytes) -> bool:
        if len(pcm) < 2:
            return False
        samples = array.array("h")
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not samples:
            return False
        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
        return rms > 100

    async def receive(self) -> TranscriptionResult:
        result = await self._results.get()
        if isinstance(result, Exception):
            raise result
        return result

    async def _receive_loop(self) -> None:
        assert self._websocket is not None
        try:
            async for raw_message in self._websocket:
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    logger.warning("OpenAI returned invalid JSON")
                    continue
                await self._dispatch(event)
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._stopping:
                logger.error(
                    "OpenAI transcription connection closed: code=%s",
                    exc.code,
                )
                await self._results.put(
                    ConnectionError("OpenAI transcription connection closed")
                )
        except Exception:
            if not self._stopping:
                logger.exception("OpenAI transcription receive loop failed")
                await self._results.put(
                    ConnectionError("OpenAI transcription receive loop failed")
                )
        finally:
            self._connected = False

    async def _dispatch(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")
        item_id = str(event.get("item_id", ""))

        if event_type == "conversation.item.input_audio_transcription.delta":
            delta = str(event.get("delta", ""))
            self._partials[item_id] = self._partials.get(item_id, "") + delta
            await self._results.put(
                TranscriptionResult(
                    text=self._partials[item_id],
                    is_final=False,
                    item_id=item_id,
                    language=self._language,
                )
            )
        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = str(event.get("transcript", ""))
            if not transcript:
                transcript = self._partials.get(item_id, "")
            self._partials.pop(item_id, None)
            await self._results.put(
                TranscriptionResult(
                    text=transcript,
                    is_final=True,
                    item_id=item_id,
                    language=self._language,
                )
            )
        elif event_type == "conversation.item.input_audio_transcription.failed":
            self._partials.pop(item_id, None)
            logger.error("OpenAI transcription failed for one speech turn")
        elif event_type == "error":
            error = event.get("error")
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            logger.error("OpenAI Realtime error: code=%s", code)

    async def stop(self) -> None:
        self._stopping = True
        self._connected = False
        if self._receive_task is not None:
            self._receive_task.cancel()
            await asyncio.gather(self._receive_task, return_exceptions=True)
            self._receive_task = None
        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None
