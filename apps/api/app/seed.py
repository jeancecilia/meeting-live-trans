"""Seed script: creates the two internal user accounts.

Production: passwords must come from SEED_ENGLISH_PASSWORD / SEED_THAI_PASSWORD.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select
from app.auth.security import hash_password
from app.database import async_session
from app.models.user import User

ENGLISH_PASSWORD = os.environ.get("SEED_ENGLISH_PASSWORD", "")
THAI_PASSWORD = os.environ.get("SEED_THAI_PASSWORD", "")
ENGLISH_EMAIL = os.environ.get("SEED_ENGLISH_EMAIL", "jeancecilia123@gmail.com").strip().lower()
THAI_EMAIL = os.environ.get("SEED_THAI_EMAIL", "umfon.14@gmail.com").strip().lower()
DEFAULT_DEV = "dev_password_change_me"


async def seed() -> None:
    app_env = os.environ.get("APP_ENV", "development")

    # Fail startup rather than creating an unusable or malformed login.
    email_adapter = TypeAdapter(EmailStr)
    email_adapter.validate_python(ENGLISH_EMAIL)
    email_adapter.validate_python(THAI_EMAIL)

    if app_env == "production":
        if not ENGLISH_PASSWORD or not THAI_PASSWORD:
            print("ERROR: SEED_ENGLISH_PASSWORD and SEED_THAI_PASSWORD must be set in production.")
            sys.exit(1)
        if ENGLISH_PASSWORD == DEFAULT_DEV or THAI_PASSWORD == DEFAULT_DEV:
            print("ERROR: Default passwords not allowed in production.")
            sys.exit(1)

    en_pw = ENGLISH_PASSWORD or DEFAULT_DEV
    th_pw = THAI_PASSWORD or DEFAULT_DEV

    async with async_session() as db:
        # English-speaking internal user — expects to see English captions
        r = await db.execute(select(User).where(User.email == ENGLISH_EMAIL))
        english_user = r.scalar_one_or_none()
        if not english_user:
            # Renaming the existing role account preserves all meeting history.
            english_user = (await db.execute(select(User).where(User.role == "host").limit(1))).scalar_one_or_none()
        if english_user:
            english_user.email = ENGLISH_EMAIL
            english_user.preferred_spoken_language = "en"
            english_user.preferred_caption_language = "en"
        else:
            db.add(User(
                email=ENGLISH_EMAIL,
                password_hash=hash_password(en_pw),
                display_name="English Speaker",
                role="host",
                preferred_spoken_language="en",
                preferred_caption_language="en",
                is_active=True,
            ))

        # Thai-speaking internal user — expects to see Thai captions
        r = await db.execute(select(User).where(User.email == THAI_EMAIL))
        thai_user = r.scalar_one_or_none()
        if not thai_user:
            thai_user = (await db.execute(select(User).where(User.role == "internal_partner").limit(1))).scalar_one_or_none()
        if thai_user:
            thai_user.email = THAI_EMAIL
            thai_user.preferred_spoken_language = "th"
            thai_user.preferred_caption_language = "th"
        else:
            db.add(User(
                email=THAI_EMAIL,
                password_hash=hash_password(th_pw),
                display_name="Thai Speaker",
                role="internal_partner",
                preferred_spoken_language="th",
                preferred_caption_language="th",
                is_active=True,
            ))

        await db.commit()
        note = " (dev)" if app_env != "production" else ""
        print(f"Seed complete. Environment: {app_env}{note}")


if __name__ == "__main__":
    asyncio.run(seed())
