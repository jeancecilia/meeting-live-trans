"""Seed script: creates the two internal user accounts.

Usage:
    python -m app.seed

Production: passwords must be set via environment variables.
Refuses to run in production with default credentials.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.database import async_session
from app.models.user import User

# Production passwords MUST come from environment variables
ENGLISH_PASSWORD = os.environ.get("SEED_ENGLISH_PASSWORD", "")
THAI_PASSWORD = os.environ.get("SEED_THAI_PASSWORD", "")

DEFAULT_DEV_PASSWORD = "dev_password_change_me"


async def seed() -> None:
    app_env = os.environ.get("APP_ENV", "development")

    # Refuse default credentials in production
    if app_env == "production":
        if not ENGLISH_PASSWORD or not THAI_PASSWORD:
            print("ERROR: SEED_ENGLISH_PASSWORD and SEED_THAI_PASSWORD must be set in production.")
            sys.exit(1)
        if ENGLISH_PASSWORD == DEFAULT_DEV_PASSWORD or THAI_PASSWORD == DEFAULT_DEV_PASSWORD:
            print("ERROR: Default seed passwords are not allowed in production.")
            sys.exit(1)

    en_password = ENGLISH_PASSWORD or DEFAULT_DEV_PASSWORD
    th_password = THAI_PASSWORD or DEFAULT_DEV_PASSWORD

    async with async_session() as db:
        # English-speaking internal user (host)
        result = await db.execute(select(User).where(User.email == "english@internal.local"))
        if not result.scalar_one_or_none():
            db.add(
                User(
                    email="english@internal.local",
                    password_hash=hash_password(en_password),
                    display_name="English Speaker",
                    role="host",
                    preferred_spoken_language="en",
                    preferred_caption_language="th",
                    is_active=True,
                )
            )

        # Thai-speaking internal user
        result = await db.execute(select(User).where(User.email == "thai@internal.local"))
        if not result.scalar_one_or_none():
            db.add(
                User(
                    email="thai@internal.local",
                    password_hash=hash_password(th_password),
                    display_name="Thai Speaker",
                    role="internal_partner",
                    preferred_spoken_language="th",
                    preferred_caption_language="en",
                    is_active=True,
                )
            )

        await db.commit()
        env_note = " (dev default)" if app_env != "production" else ""
        print(f"Seed completed: two internal accounts created. Environment: {app_env}{env_note}")


if __name__ == "__main__":
    asyncio.run(seed())
