"""Seed script: creates the two internal user accounts.

Production: passwords must come from SEED_ENGLISH_PASSWORD / SEED_THAI_PASSWORD.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from app.auth.security import hash_password
from app.database import async_session
from app.models.user import User

ENGLISH_PASSWORD = os.environ.get("SEED_ENGLISH_PASSWORD", "")
THAI_PASSWORD = os.environ.get("SEED_THAI_PASSWORD", "")
DEFAULT_DEV = "dev_password_change_me"


async def seed() -> None:
    app_env = os.environ.get("APP_ENV", "development")

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
        r = await db.execute(select(User).where(User.email == "english@internal.local"))
        if not r.scalar_one_or_none():
            db.add(User(
                email="english@internal.local",
                password_hash=hash_password(en_pw),
                display_name="English Speaker",
                role="host",
                preferred_spoken_language="en",
                preferred_caption_language="en",
                is_active=True,
            ))

        # Thai-speaking internal user — expects to see Thai captions
        r = await db.execute(select(User).where(User.email == "thai@internal.local"))
        if not r.scalar_one_or_none():
            db.add(User(
                email="thai@internal.local",
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
