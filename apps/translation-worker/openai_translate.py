"""OpenAI Realtime speech-to-speech translation transcript provider."""

from __future__ import annotations

import array
import asyncio
import base64
import json
import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import quote

import websockets

from pipeline import TranscriptionResult

logger = logging.getLogger("translation-worker.openai-translate")


class OpenAIRealtimeTranslateProvider:
    """Stream PCM audio and expose cumulative translated transcript revisions.

    The translation endpoint emits transcript deltas without an utterance-complete
    event. A local speech-silence plus output-idle boundary therefore turns each
    stable group of deltas into one final caption.
    """

    def __init__(
        self,
        api_key: str,
        target_language: str,
        model: str = "gpt-realtime-translate",
        base_url: str | None = None,
        max_connect_attempts: int = 3,
        final_silence_ms: int | None = None,
        output_idle_ms: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._target_language = target_language
        self._model = model
        self._base_url = (
            base_url
            or os.environ.get("OPENAI_REALTIME_TRANSLATE_URL")
            or "wss://api.openai.com/v1/realtime/translations"
        )
        self._max_connect_attempts = max_connect_attempts
        self._final_silence_ms = final_silence_ms or int(
            os.environ.get("OPENAI_TRANSLATE_FINAL_SILENCE_MS", "700")
        )
        self._output_idle_ms = output_idle_ms or int(
            os.environ.get("OPENAI_TRANSLATE_OUTPUT_IDLE_MS", "1500")
        )
        self._source_language = "en"
        self._websocket: Any | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._boundary_task: asyncio.Task[None] | None = None
        self._results: asyncio.Queue[TranscriptionResult | Exception] = asyncio.Queue()
        self._connected = False
        self._stopping = False
        self._session_close_sent = False
        self._closed_event = asyncio.Event()
        self._partial_lock = asyncio.Lock()
        self._partial_text = ""
        self._partial_id = ""
        self._carry_text = ""
        self._carry_id = ""
        self._carry_finalized_at = 0.0
        self._late_revision_ms = int(
            os.environ.get("OPENAI_TRANSLATE_LATE_REVISION_MS", "10000")
        )
        self._last_signal_time = 0.0
        self._last_delta_time = 0.0
        self._finalized_through_signal_time = 0.0
        self._final_count = 0
        self._error_queued = False

    async def start(self, language: str) -> None:
        if not self._api_key or self._api_key == "sk-change-me":
            raise RuntimeError("OPENAI_API_KEY is not configured")
        if language not in {"en", "th"}:
            raise ValueError(f"Unsupported source language: {language}")
        if self._target_language not in {"en", "th"}:
            raise ValueError(
                f"Unsupported translation language: {self._target_language}"
            )
        if language == self._target_language:
            raise ValueError("Source and translation languages must differ")

        self._source_language = language
        self._stopping = False
        await self._connect()

    async def _connect(self) -> None:
        separator = "&" if "?" in self._base_url else "?"
        url = f"{self._base_url}{separator}model={quote(self._model)}"
        last_error: Exception | None = None

        for attempt in range(1, self._max_connect_attempts + 1):
            try:
                self._websocket = await websockets.connect(
                    url,
                    additional_headers={"Authorization": f"Bearer {self._api_key}"},
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
                                "audio": {"output": {"language": self._target_language}}
                            },
                        }
                    )
                )
                self._connected = True
                self._session_close_sent = False
                self._closed_event.clear()
                self._receive_task = asyncio.create_task(
                    self._receive_loop(), name="openai-translation-receive"
                )
                self._boundary_task = asyncio.create_task(
                    self._boundary_loop(), name="openai-translation-boundary"
                )
                logger.info(
                    "OpenAI direct translation connected: model=%s source=%s target=%s",
                    self._model,
                    self._source_language,
                    self._target_language,
                )
                return
            except Exception as exc:
                last_error = exc
                self._connected = False
                logger.warning(
                    "OpenAI direct translation connection failed: "
                    "attempt=%d/%d error=%s",
                    attempt,
                    self._max_connect_attempts,
                    type(exc).__name__,
                )
                if attempt < self._max_connect_attempts:
                    await asyncio.sleep(min(2 ** (attempt - 1), 4))

        raise RuntimeError(
            "Unable to connect to OpenAI Realtime translation"
        ) from last_error

    async def append_audio(self, pcm: bytes) -> None:
        if not pcm:
            return
        if not self._connected or self._websocket is None:
            raise ConnectionError("OpenAI direct translation is disconnected")

        if self._has_signal(pcm):
            now = time.monotonic()
            if (
                self._last_signal_time > 0
                and (now - self._last_signal_time) * 1_000 >= self._final_silence_ms
            ):
                self._carry_text = ""
                self._carry_id = ""
                self._carry_finalized_at = 0.0
            self._last_signal_time = now

        try:
            await self._websocket.send(
                json.dumps(
                    {
                        "type": "session.input_audio_buffer.append",
                        "audio": base64.b64encode(pcm).decode("ascii"),
                    }
                )
            )
        except Exception as exc:
            self._connected = False
            await self._queue_error_once(
                ConnectionError("Failed to stream audio to direct translation")
            )
            raise ConnectionError(
                "Failed to stream audio to direct translation"
            ) from exc

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
                    logger.warning("OpenAI direct translation returned invalid JSON")
                    continue
                if await self._dispatch(event):
                    break
        except asyncio.CancelledError:
            raise
        except websockets.ConnectionClosed as exc:
            if not self._stopping and not self._session_close_sent:
                logger.error(
                    "OpenAI direct translation connection closed: code=%s", exc.code
                )
                await self._queue_error_once(
                    ConnectionError("OpenAI direct translation connection closed")
                )
        except Exception:
            if not self._stopping:
                logger.exception("OpenAI direct translation receive loop failed")
                await self._queue_error_once(
                    ConnectionError("OpenAI direct translation receive loop failed")
                )
        finally:
            self._connected = False
            self._closed_event.set()

    async def _dispatch(self, event: dict[str, Any]) -> bool:
        event_type = str(event.get("type", ""))
        if event_type == "session.output_transcript.delta":
            delta = str(event.get("delta", ""))
            if not delta:
                return False
            async with self._partial_lock:
                if not self._partial_id:
                    now = time.monotonic()
                    if (
                        self._carry_id
                        and (now - self._carry_finalized_at) * 1_000
                        <= self._late_revision_ms
                    ):
                        self._partial_id = self._carry_id
                        self._partial_text = self._carry_text
                    else:
                        self._partial_id = uuid.uuid4().hex
                self._partial_text += delta
                self._last_delta_time = time.monotonic()
                result = TranscriptionResult(
                    text=self._partial_text,
                    is_final=False,
                    item_id=self._partial_id,
                    language=self._target_language,
                )
            await self._results.put(result)
        elif event_type == "error":
            error = event.get("error")
            code = (
                error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            )
            logger.error("OpenAI direct translation error: code=%s", code)
            await self._queue_error_once(
                RuntimeError(f"OpenAI direct translation request failed: {code}")
            )
        elif event_type == "session.closed":
            await self._finalize_current()
            self._closed_event.set()
            return True
        return False

    async def _boundary_loop(self) -> None:
        try:
            while not self._stopping and not self._session_close_sent:
                await asyncio.sleep(0.05)
                now = time.monotonic()
                if (
                    self._partial_text
                    and self._last_signal_time > 0
                    and (now - self._last_signal_time) * 1_000 >= self._final_silence_ms
                    and (now - self._last_delta_time) * 1_000 >= self._output_idle_ms
                ):
                    await self._finalize_current()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Direct translation boundary monitor failed")
            await self._queue_error_once(
                RuntimeError("Direct translation boundary monitor failed")
            )

    async def _finalize_current(self) -> bool:
        async with self._partial_lock:
            text = self._partial_text.strip()
            item_id = self._partial_id
            if not text or not item_id:
                return False
            self._partial_text = ""
            self._partial_id = ""
            self._last_delta_time = 0.0
            self._finalized_through_signal_time = self._last_signal_time
            self._final_count += 1
            self._carry_text = text
            self._carry_id = item_id
            self._carry_finalized_at = time.monotonic()

        await self._results.put(
            TranscriptionResult(
                text=text,
                is_final=True,
                item_id=item_id,
                language=self._target_language,
            )
        )
        return True

    async def commit_pending(self) -> bool:
        final_count_before_close = self._final_count
        pending_audio = (
            self._last_signal_time > self._finalized_through_signal_time
            or bool(self._partial_text)
        )
        if self._websocket is None or self._session_close_sent:
            return pending_audio

        self._session_close_sent = True
        try:
            await self._websocket.send(json.dumps({"type": "session.close"}))
            await asyncio.wait_for(self._closed_event.wait(), timeout=10)
        except TimeoutError:
            logger.warning("Timed out waiting for direct translation session close")
        except Exception as exc:
            await self._queue_error_once(
                ConnectionError("Failed to close direct translation session")
            )
            raise ConnectionError("Failed to close direct translation session") from exc
        return pending_audio or self._final_count > final_count_before_close

    async def _queue_error_once(self, error: Exception) -> None:
        if not self._error_queued:
            self._error_queued = True
            await self._results.put(error)

    @staticmethod
    def _has_signal(pcm: bytes) -> bool:
        if len(pcm) < 2:
            return False
        samples = array.array("h")
        samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
        if not samples:
            return False
        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
        return rms > 100

    async def stop(self) -> None:
        self._stopping = True
        if self._boundary_task is not None:
            self._boundary_task.cancel()
            await asyncio.gather(self._boundary_task, return_exceptions=True)
            self._boundary_task = None
        if self._receive_task is not None:
            self._receive_task.cancel()
            await asyncio.gather(self._receive_task, return_exceptions=True)
            self._receive_task = None
        if self._websocket is not None:
            await self._websocket.close()
            self._websocket = None
        self._connected = False
