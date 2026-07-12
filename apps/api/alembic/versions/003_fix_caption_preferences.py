"""Fix existing user caption preferences — swap direction

Revision ID: 003
Revises: 002
Create Date: 2026-07-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET preferred_caption_language = 'en' WHERE email = 'english@meetingtest.com'")
    op.execute("UPDATE users SET preferred_caption_language = 'th' WHERE email = 'thai@meetingtest.com'")


def downgrade() -> None:
    op.execute("UPDATE users SET preferred_caption_language = 'th' WHERE email = 'english@internal.local'")
    op.execute("UPDATE users SET preferred_caption_language = 'en' WHERE email = 'thai@internal.local'")
