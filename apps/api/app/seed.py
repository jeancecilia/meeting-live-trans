"""Seed script: creates the two internal user accounts.

Usage:
    python -m app.seed
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


async def seed() -> None:
    async with async_session() as db:  # type: AsyncSession
        # English-speaking internal user (host)
        result = await db.execute(select(User).where(User.email == "english@internal.local"))
        if not result.scalar_one_or_none():
            db.add(
                User(
                    email="english@internal.local",
                    password_hash=hash_password("Password123!"),
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
                    password_hash=hash_password("Password123!"),
                    display_name="Thai Speaker",
                    role="internal_partner",
                    preferred_spoken_language="th",
                    preferred_caption_language="en",
                    is_active=True,
                )
            )

        await db.commit()
        print("Seed completed: two internal accounts created.")


if __name__ == "__main__":
    asyncio.run(seed())
