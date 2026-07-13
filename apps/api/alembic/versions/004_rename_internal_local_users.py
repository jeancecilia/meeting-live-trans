"""Rename internal.local users to meetingtest.com

Revision ID: 004
Revises: 003
Create Date: 2026-07-12
"""
from typing import Sequence, Union
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. English User
    # Re-map any data associated with the duplicate new account (if created by seed) to the old account
    op.execute("""
        UPDATE meetings 
        SET created_by = (SELECT id FROM users WHERE email = 'english@internal.local')
        WHERE created_by = (SELECT id FROM users WHERE email = 'english@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'english@internal.local')
    """)
    op.execute("""
        UPDATE meeting_participants 
        SET user_id = (SELECT id FROM users WHERE email = 'english@internal.local')
        WHERE user_id = (SELECT id FROM users WHERE email = 'english@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'english@internal.local')
    """)
    op.execute("""
        UPDATE audit_logs 
        SET actor_id = (SELECT id FROM users WHERE email = 'english@internal.local')
        WHERE actor_id = (SELECT id FROM users WHERE email = 'english@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'english@internal.local')
    """)
    
    # Delete the duplicate new account if the old one exists
    op.execute("""
        DELETE FROM users 
        WHERE email = 'english@meetingtest.com' 
          AND EXISTS (SELECT 1 FROM users WHERE email = 'english@internal.local')
    """)
    
    # Rename old to new and fix caption preference
    op.execute("""
        UPDATE users 
        SET email = 'english@meetingtest.com', preferred_caption_language = 'en'
        WHERE email = 'english@internal.local'
    """)
    # Also ensure the seeded user gets the correct preference if it was a fresh DB (old never existed)
    op.execute("""
        UPDATE users 
        SET preferred_caption_language = 'en'
        WHERE email = 'english@meetingtest.com'
    """)


    # 2. Thai User
    # Re-map any data associated with the duplicate new account
    op.execute("""
        UPDATE meetings 
        SET created_by = (SELECT id FROM users WHERE email = 'thai@internal.local')
        WHERE created_by = (SELECT id FROM users WHERE email = 'thai@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'thai@internal.local')
    """)
    op.execute("""
        UPDATE meeting_participants 
        SET user_id = (SELECT id FROM users WHERE email = 'thai@internal.local')
        WHERE user_id = (SELECT id FROM users WHERE email = 'thai@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'thai@internal.local')
    """)
    op.execute("""
        UPDATE audit_logs 
        SET actor_id = (SELECT id FROM users WHERE email = 'thai@internal.local')
        WHERE actor_id = (SELECT id FROM users WHERE email = 'thai@meetingtest.com')
          AND EXISTS (SELECT 1 FROM users WHERE email = 'thai@internal.local')
    """)
    
    # Delete the duplicate new account if the old one exists
    op.execute("""
        DELETE FROM users 
        WHERE email = 'thai@meetingtest.com' 
          AND EXISTS (SELECT 1 FROM users WHERE email = 'thai@internal.local')
    """)
    
    # Rename old to new and fix caption preference
    op.execute("""
        UPDATE users 
        SET email = 'thai@meetingtest.com', preferred_caption_language = 'th'
        WHERE email = 'thai@internal.local'
    """)
    # Also ensure the seeded user gets the correct preference if it was a fresh DB (old never existed)
    op.execute("""
        UPDATE users 
        SET preferred_caption_language = 'th'
        WHERE email = 'thai@meetingtest.com'
    """)


def downgrade() -> None:
    # Revert emails back to internal.local and reverse caption preferences as they were in 002
    op.execute("UPDATE users SET email = 'english@internal.local', preferred_caption_language = 'th' WHERE email = 'english@meetingtest.com'")
    op.execute("UPDATE users SET email = 'thai@internal.local', preferred_caption_language = 'en' WHERE email = 'thai@meetingtest.com'")
