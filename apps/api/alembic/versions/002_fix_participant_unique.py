"""Fix participant identity uniqueness — allow same identity across meetings

Revision ID: 002
Revises: 001
Create Date: 2026-07-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the global unique constraint on livekit_identity
    op.drop_constraint("meeting_participants_livekit_identity_key", "meeting_participants", type_="unique")

    # Add composite unique: participant can only appear once per meeting
    op.create_unique_constraint(
        "uq_meeting_participant_identity",
        "meeting_participants",
        ["meeting_id", "livekit_identity"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_meeting_participant_identity", "meeting_participants", type_="unique")
    op.create_unique_constraint(
        "meeting_participants_livekit_identity_key",
        "meeting_participants",
        ["livekit_identity"],
    )
