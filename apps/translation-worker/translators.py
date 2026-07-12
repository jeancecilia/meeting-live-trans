"""
Translation providers (MTG-033).

Two implementations:
1. OpenAIRealtimeTranslateProvider — uses gpt-realtime-translate for direct audio→translation
2. OpenAITranscribeThenTranslateProvider — gpt-realtime-whisper + text translation (fallback)

Features:
- Debounce partial transcript translation
- Cancel stale partial translations
- Final translation always replaces partial
- Model selection via environment config
"""

import asyncio
import logging
from typing import Optional

from pipeline import TranslationProvider, TranslationResult

logger = logging.getLogger("translation-worker.translators")


# ──── Direct translate provider ────


class OpenAIRealtimeTranslateProvider(TranslationProvider):
    """
    Uses gpt-realtime-translate for direct audio-to-translated-transcript.

    This provider is preferred when verified, as it handles both
    transcription and translation in a single model call.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini-realtime") -> None:
        self._api_key = api_key
        self._model = model
        self._latest_revision: int = 0
        self._pending_partial_tasks: dict[int, asyncio.Task] = {}

    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult:
        self._latest_revision = max(self._latest_revision, revision)
        # Direct translate handles this in the realtime API
        return TranslationResult(
            text=text,
            source_language=source_language,
            target_language=target_language,
            revision=revision,
            is_final=False,
        )

    async def translate_final(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        return TranslationResult(
            text=text,
            source_language=source_language,
            target_language=target_language,
            revision=self._latest_revision + 1,
            is_final=True,
        )


# ──── Transcribe-then-translate fallback provider ────


class OpenAITranscribeThenTranslateProvider(TranslationProvider):
    """
    Fallback pipeline:
    1. Audio → gpt-realtime-whisper (transcription)
    2. Text → OpenAI text model (translation)

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
        self._partial_text: str = ""

    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult:
        """
        Debounced partial translation.
        Cancels any stale partial translation before starting a new one.
        """
        self._latest_revision = max(self._latest_revision, revision)

        # Cancel stale partial tasks
        for old_rev, task in list(self._pending_partial_tasks.items()):
            if old_rev < self._latest_revision:
                task.cancel()
                del self._pending_partial_tasks[old_rev]

        self._partial_text = text

        # Debounce: wait for more text before translating
        await asyncio.sleep(self._partial_debounce_ms / 1000)

        # Check if a newer revision arrived during debounce
        if revision < self._latest_revision:
            raise asyncio.CancelledError("Stale partial translation")

        translated = await self._translate_text(
            text, source_language, target_language
        )

        return TranslationResult(
            text=translated,
            source_language=source_language,
            target_language=target_language,
            revision=revision,
            is_final=False,
        )

    async def translate_final(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        """Translate the completed utterance. This always runs."""
        # Cancel all pending partials
        for task in self._pending_partial_tasks.values():
            task.cancel()
        self._pending_partial_tasks.clear()

        translated = await self._translate_text(
            text, source_language, target_language
        )

        self._latest_revision += 1
        return TranslationResult(
            text=translated,
            source_language=source_language,
            target_language=target_language,
            revision=self._latest_revision,
            is_final=True,
        )

    async def _translate_text(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> str:
        """Call OpenAI text model for translation."""
        import httpx

        language_names = {"en": "English", "th": "Thai"}

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
                                f"You are a translator. Translate from "
                                f"{language_names.get(source_language, source_language)} to "
                                f"{language_names.get(target_language, target_language)}. "
                                f"Preserve names, numbers, dates, and currencies exactly. "
                                f"Only return the translated text, no explanations."
                            ),
                        },
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 1024,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
