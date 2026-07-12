"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def valid_invite_token() -> str:
    """A valid-looking invite token for tests."""
    return "test_valid_token_abc123"


@pytest.fixture
def expired_invite_token() -> str:
    """An expired invite token for tests."""
    return "test_expired_token_xyz789"
