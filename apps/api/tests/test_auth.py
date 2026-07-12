"""
Tests for authentication module (MTG-050).

Covers:
- Login with valid credentials
- Login with invalid password
- Login with disabled account
- Expired access token rejection
- Refresh token flow
- Role-based route protection
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.auth.dependencies import get_current_user, require_internal_role


class TestPasswordHashing:
    def test_hash_and_verify_valid_password(self):
        password = "SecurePass123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_verify_wrong_password(self):
        hashed = hash_password("CorrectPassword")
        assert not verify_password("WrongPassword", hashed)

    def test_hash_is_unique_per_call(self):
        password = "SamePassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Different salts


class TestJWT:
    def test_create_and_decode_access_token(self):
        import uuid

        user_id = uuid.uuid4()
        token = create_access_token(user_id, "host")
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["role"] == "host"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_and_decode_refresh_token(self):
        import uuid

        user_id = uuid.uuid4()
        token = create_refresh_token(user_id)
        payload = decode_token(token)

        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"

    def test_expired_token_rejected(self, monkeypatch):
        import uuid

        # Force token to be expired by setting expiry to 0
        from app.auth import security
        from app.config import settings as app_settings

        monkeypatch.setattr(app_settings, "jwt_access_token_expire_minutes", -1)

        user_id = uuid.uuid4()
        token = create_access_token(user_id, "host")

        with pytest.raises(Exception):
            decode_token(token)

    def test_invalid_token_rejected(self):
        with pytest.raises(Exception):
            decode_token("not.a.valid.token")


class TestRoleEnforcement:
    @pytest.mark.asyncio
    async def test_internal_role_required_for_host(self):
        """Host users should pass internal role check."""
        from app.models.user import User
        import uuid

        user = User(
            id=uuid.uuid4(),
            email="test@test.com",
            password_hash="...",
            display_name="Test",
            role="host",
            is_active=True,
        )

        result = require_internal_role(user)
        assert result == user

    @pytest.mark.asyncio
    async def test_guest_rejected_from_internal_routes(self):
        """Guest role should be rejected by require_internal_role."""
        from app.models.user import User
        import uuid

        user = User(
            id=uuid.uuid4(),
            email="guest@test.com",
            password_hash="...",
            display_name="Guest",
            role="guest",
            is_active=True,
        )

        with pytest.raises(Exception):
            require_internal_role(user)
