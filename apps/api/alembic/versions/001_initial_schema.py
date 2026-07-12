"""Initial schema — users, meetings, invites, participants, audit_logs

Revision ID: 001
Revises:
Create Date: 2026-07-12
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="internal_partner",
        ),
        sa.Column(
            "preferred_spoken_language",
            sa.String(5),
            nullable=False,
            server_default="en",
        ),
        sa.Column(
            "preferred_caption_language",
            sa.String(5),
            nullable=False,
            server_default="en",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── meetings ──
    op.create_table(
        "meetings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_name", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="created",
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── meeting_invites ──
    op.create_table(
        "meeting_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("token_hash", sa.String(128), unique=True, nullable=False),
        sa.Column("guest_name", sa.String(100), nullable=False),
        sa.Column(
            "expected_spoken_language",
            sa.String(5),
            nullable=False,
            server_default="en",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── meeting_participants ──
    op.create_table(
        "meeting_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("guest_identity", sa.String(100), nullable=True),
        sa.Column("livekit_identity", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("spoken_language", sa.String(5), nullable=False),
        sa.Column("caption_language", sa.String(5), nullable=True),
        sa.Column(
            "caption_access",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── audit_logs ──
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False, index=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # ── constraints ──
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('host', 'internal_partner')",
    )
    op.create_check_constraint(
        "ck_users_language",
        "users",
        "preferred_spoken_language IN ('en', 'th') AND preferred_caption_language IN ('en', 'th')",
    )
    op.create_check_constraint(
        "ck_meetings_status",
        "meetings",
        "status IN ('created', 'active', 'ended')",
    )
    op.create_check_constraint(
        "ck_participants_role",
        "meeting_participants",
        "role IN ('host', 'internal_partner', 'guest')",
    )
    op.create_check_constraint(
        "ck_participants_language",
        "meeting_participants",
        "spoken_language IN ('en', 'th')",
    )
    op.create_check_constraint(
        "ck_invites_language",
        "meeting_invites",
        "expected_spoken_language IN ('en', 'th')",
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("meeting_participants")
    op.drop_table("meeting_invites")
    op.drop_table("meetings")
    op.drop_table("users")
