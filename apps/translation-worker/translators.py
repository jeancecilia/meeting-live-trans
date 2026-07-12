"""
Translation providers (MTG-033).

Fallback provider only for MVP:
Audio → gpt-realtime-whisper → text transcript → OpenAI translation → caption

The direct gpt-realtime-translate provider is a future enhancement.
"""

import asyncio
import logging
from typing import Optional

from pipeline import TranslationProvider, TranslationResult

logger = logging.getLogger("translation-worker.translators")


class OpenAITranscribeThenTranslateProvider(TranslationProvider):
    """
    Fallback pipeline:
    1. Audio → gpt-realtime-whisper (handled by transcription provider)
    2. Text → OpenAI chat completions for translation

    Implements debouncing and stale-request cancellation.
    """

    def __init__(
        self,
        api_key: str,
        translation_model: str = "gpt-4o-mini",
        partial_debounce_ms: int = 500,
    ) -> None:
        self._api_key = api_key
        self._translation_model = translation_model
        self._partial_debounce_ms = partial_debounce_ms
        self._latest_revision: int = 0
        self._pending_partial_tasks: dict[int, asyncio.Task] = {}

    async def translate_partial(
        self, text: str, source_language: str, target_language: str, revision: int
    ) -> TranslationResult:
        self._latest_revision = max(self._latest_revision, revision)

        for old_rev, task in list(self._pending_partial_tasks.items()):
            if old_rev < self._latest_revision:
                task.cancel()
                del self._pending_partial_tasks[old_rev]

        await asyncio.sleep(self._partial_debounce_ms / 1000)

        if revision < self._latest_revision:
            raise asyncio.CancelledError("Stale partial translation")

        translated = await self._translate_text(text, source_language, target_language)
        return TranslationResult(
            text=translated, source_language=source_language,
            target_language=target_language, revision=revision, is_final=False,
        )

    async def translate_final(
        self, text: str, source_language: str, target_language: str
    ) -> TranslationResult:
        for task in self._pending_partial_tasks.values():
            task.cancel()
        self._pending_partial_tasks.clear()

        translated = await self._translate_text(text, source_language, target_language)
        self._latest_revision += 1
        return TranslationResult(
            text=translated, source_language=source_language,
            target_language=target_language, revision=self._latest_revision, is_final=True,
        )

    async def _translate_text(self, text: str, source_language: str, target_language: str) -> str:
        import httpx

        language_names = {"en": "English", "th": "Thai"}
        src_name = language_names.get(source_language, source_language)
        tgt_name = language_names.get(target_language, target_language)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._translation_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                f"Translate from {src_name} to {tgt_name}. "
                                f"Preserve names, numbers, dates, and currencies exactly. "
                                f"Return only the translated text."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
