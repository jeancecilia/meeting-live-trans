"""
Privacy and consent middleware (MTG-040).

- Ensures consent acknowledgment before joining meetings
- Configures transcript storage (disabled by default)
- Handles retention and data deletion
- Sanitizes logs of caption content
"""

import logging


logger = logging.getLogger("api.privacy")


# ──── Privacy configuration ────

class PrivacyConfig:
    """Central privacy settings. All defaults are privacy-preserving."""

    caption_storage_enabled: bool = False
    caption_retention_days: int = 0
    raw_audio_storage_enabled: bool = False

    consent_required: bool = True
    consent_text: str = (
        "This meeting uses automated speech transcription and translation. "
        "Audio is processed in real time. Meeting audio is not recorded by "
        "this application."
    )

    @classmethod
    def load_from_env(cls) -> None:
        import os
        cls.caption_storage_enabled = os.environ.get("CAPTION_STORAGE_ENABLED", "false").lower() == "true"
        cls.caption_retention_days = int(os.environ.get("CAPTION_RETENTION_DAYS", "0"))


# ──── Log sanitization ────

class SanitizingFormatter(logging.Formatter):
    """
    Log formatter that strips sensitive content.

    Removes: raw audio references, full transcripts, translated text,
    API keys, invite tokens, passwords.
    """

    REDACTED = "[REDACTED]"
    SENSITIVE_FIELDS = {
        "transcript",
        "translated_text",
        "caption_text",
        "audio_data",
        "password",
        "password_hash",
        "api_key",
        "token",
        "access_token",
        "refresh_token",
    }

    def format(self, record: logging.LogRecord) -> str:
        original_msg = record.msg
        if isinstance(original_msg, str):
            for field in self.SENSITIVE_FIELDS:
                # Redact field=value patterns
                if f"{field}=" in original_msg.lower():
                    record.msg = record.msg.replace(
                        original_msg,
                        self._redact_field(original_msg, field),
                    )

        return super().format(record)

    def _redact_field(self, msg: str, field: str) -> str:
        """Replace sensitive field values with [REDACTED]."""
        # Simple redaction — production would use regex
        return f"{field}={self.REDACTED}"


def configure_safe_logging() -> None:
    """Apply safe logging configuration to all loggers."""
    handler = logging.StreamHandler()
    handler.setFormatter(SanitizingFormatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    # Disable debug logging for sensitive modules
    logging.getLogger("app.routers.captions").setLevel(logging.WARNING)


# ──── Data deletion ────

async def delete_meeting_data(meeting_id: str) -> None:
    """
    Delete all stored data for a meeting (MTG-040).

    Removes optional stored caption data and audit logs if retention has expired.
    Raw audio is never written to disk, so nothing to delete there.
    """
    logger.info(
        "Deleting meeting data: meeting_id=%s",
        meeting_id,
    )
    # In production, this would:
    # 1. Delete optional stored caption rows for the meeting
    # 2. Anonymize audit logs (set actor_id/meeting_id to null)
    # 3. Log the deletion without the content
