"""Unit tests for active_turns: per-user concurrent AutoPilot turn tracking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.copilot import active_turns as active_turns_module
from backend.copilot.active_turns import (
    MAX_CONCURRENT_TURNS_PER_USER,
    count_active_turns,
    release_turn_slot,
    try_acquire_turn_slot,
)


@pytest.mark.asyncio
async def test_try_acquire_returns_true_when_under_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lua returns 1 → caller gets True (slot acquired)."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=1)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    acquired = await try_acquire_turn_slot("user-1", "session-a", limit=15)
    assert acquired is True


@pytest.mark.asyncio
async def test_try_acquire_returns_false_when_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lua returns 0 (limit reached) → caller gets False."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=0)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    acquired = await try_acquire_turn_slot("user-1", "session-a", limit=15)
    assert acquired is False


@pytest.mark.asyncio
async def test_try_acquire_fails_open_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis errors return True (fail-open) so a brown-out doesn't 429 every user."""
    monkeypatch.setattr(
        active_turns_module,
        "get_redis_async",
        AsyncMock(side_effect=ConnectionError("down")),
    )

    acquired = await try_acquire_turn_slot("user-1", "session-a", limit=15)
    assert acquired is True


@pytest.mark.asyncio
async def test_release_calls_zrem(monkeypatch: pytest.MonkeyPatch) -> None:
    """release_turn_slot ZREMs the session_id from the user's sorted set."""
    redis_mock = MagicMock()
    redis_mock.zrem = AsyncMock(return_value=1)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    await release_turn_slot("user-1", "session-a")
    redis_mock.zrem.assert_called_once()
    args, _ = redis_mock.zrem.call_args
    assert args[1] == "session-a"
    assert "user-1" in args[0]


@pytest.mark.asyncio
async def test_release_swallows_redis_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis errors during release are logged, not raised — slot will be
    swept by the next try_acquire's stale-cutoff."""
    monkeypatch.setattr(
        active_turns_module,
        "get_redis_async",
        AsyncMock(side_effect=ConnectionError("down")),
    )

    await release_turn_slot("user-1", "session-a")  # must not raise


@pytest.mark.asyncio
async def test_count_active_turns_sweeps_then_returns_zcard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """count_active_turns drops stale entries before reading ZCARD."""
    redis_mock = MagicMock()
    redis_mock.zremrangebyscore = AsyncMock(return_value=2)
    redis_mock.zcard = AsyncMock(return_value=5)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    count = await count_active_turns("user-1")
    assert count == 5
    redis_mock.zremrangebyscore.assert_called_once()
    redis_mock.zcard.assert_called_once()


@pytest.mark.asyncio
async def test_count_active_turns_returns_zero_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        active_turns_module,
        "get_redis_async",
        AsyncMock(side_effect=ConnectionError("down")),
    )

    assert await count_active_turns("user-1") == 0


def test_default_limit_constant_is_15() -> None:
    """SECRT-2335 hard cap. If you change this, update the user-facing
    error message and the linear ticket."""
    assert MAX_CONCURRENT_TURNS_PER_USER == 15
