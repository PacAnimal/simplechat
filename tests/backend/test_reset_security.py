"""Tests for the reset endpoint access control."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.asyncio


def _make_db_mock():
    """AsyncSession mock that handles .execute(...).scalars().all() chain."""
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    db = AsyncMock()
    db.execute.return_value = execute_result
    return db


async def test_reset_requires_secret_header_when_configured():
    import backend.api.testing as m

    original = m.settings.reset_secret
    m.settings.reset_secret = "correct-secret"
    try:
        mock_db = _make_db_mock()

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


async def test_reset_blocked_when_secret_not_configured():
    import backend.api.testing as m

    original = m.settings.reset_secret
    m.settings.reset_secret = None
    try:
        mock_db = _make_db_mock()
        # no secret configured → always 403 (fail closed)
        with pytest.raises(HTTPException) as exc_info:
            await m.reset_db(db=mock_db, x_reset_secret=None)
        assert exc_info.value.status_code == 403
    finally:
        m.settings.reset_secret = original
