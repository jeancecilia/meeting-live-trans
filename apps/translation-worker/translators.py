"""Text translation provider used after realtime speech transcription."""

from __future__ import annotations

import os

import httpx

from pipeline import TranslationResult

LANGUAGE_NAMES = {"en": "English", "th": "Thai"}


class OpenAITextTranslationProvider:
    """Translate completed speech turns without retaining conversation state."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (
            base_url
            or os.environ.get("OPENAI_API_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self._client = httpx.AsyncClient(timeout=30.0)

    async def translate_partial(
        self,
        text: str,
        source_language: str,
        target_language: str,
        revision: int,
    ) -> TranslationResult:
        return await self._translate(text, source_language, target_language)

    async def translate_final(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        return await self._translate(text, source_language, target_language)

    async def _translate(
        self,
        text: str,
        source_language: str,
        target_language: str,
    ) -> TranslationResult:
        if not self._api_key or self._api_key == "sk-change-me":
            raise RuntimeError("OPENAI_API_KEY is not configured")
        if not text.strip():
            return TranslationResult(
                text="",
                source_language=source_language,
                target_language=target_language,
            )

        source_name = LANGUAGE_NAMES.get(source_language, source_language)
        target_name = LANGUAGE_NAMES.get(target_language, target_language)

        response = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Translate spoken {source_name} into natural {target_name}. "
                            "The input may be an incomplete live-speech fragment. "
                            "Preserve names, numbers, dates, email addresses, URLs, "
                            "currencies, and technical terminology accurately. "
                            "Return only the translation, without explanations."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0.1,
            },
        )
        response.raise_for_status()
        payload = response.json()

        translated_text = payload["choices"][0]["message"]["content"].strip()
        return TranslationResult(
            text=translated_text,
            source_language=source_language,
            target_language=target_language,
        )

    async def close(self) -> None:
        await self._client.aclose()
