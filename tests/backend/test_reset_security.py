"""Tests for the reset endpoint access control."""
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


async def test_reset_requires_secret_header_when_configured():
    import backend.api.testing as m
    original = m.settings.reset_secret
    m.settings.reset_secret = "correct-secret"
    try:
        mock_db = AsyncMock()

        # wrong secret → 403
        with pytest.raises(HTTPException) as exc_info:
            await m.reset_db(db=mock_db, x_reset_secret="wrong-secret")
        assert exc_info.value.status_code == 403

        # missing header → 403
        with pytest.raises(HTTPException) as exc_info2:
            await m.reset_db(db=mock_db, x_reset_secret=None)
        assert exc_info2.value.status_code == 403

        # correct secret → succeeds
        await m.reset_db(db=mock_db, x_reset_secret="correct-secret")
        mock_db.commit.assert_awaited()

    finally:
        m.settings.reset_secret = original


async def test_reset_allows_without_header_when_secret_not_configured():
    import backend.api.testing as m
    original = m.settings.reset_secret
    m.settings.reset_secret = None
    try:
        mock_db = AsyncMock()
        # no secret configured → no auth required
        await m.reset_db(db=mock_db, x_reset_secret=None)
        mock_db.commit.assert_awaited()
    finally:
        m.settings.reset_secret = original
