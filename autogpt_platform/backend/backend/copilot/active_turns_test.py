"""Unit tests for active_turns: per-user concurrent AutoPilot turn tracking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.copilot import active_turns as active_turns_module
from backend.copilot.active_turns import (
    MAX_CONCURRENT_TURNS_PER_USER,
    ConcurrentTurnLimitError,
    acquire_turn_slot,
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
    """Hard cap. If you change this, update the user-facing
    error message and the linear ticket."""
    assert MAX_CONCURRENT_TURNS_PER_USER == 15


# ── acquire_turn_slot context manager ─────────────────────────────────


@pytest.mark.asyncio
async def test_acquire_turn_slot_releases_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slot is auto-released when the with-body raises before ``slot.keep()``."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.zrem = AsyncMock(return_value=1)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    with pytest.raises(RuntimeError, match="downstream blew up"):
        async with acquire_turn_slot("user-1", "session-a", limit=15):
            raise RuntimeError("downstream blew up")

    redis_mock.zrem.assert_called_once()


@pytest.mark.asyncio
async def test_acquire_turn_slot_keeps_when_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``slot.keep()`` transfers ownership — slot is NOT released on exit."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.zrem = AsyncMock(return_value=1)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    async with acquire_turn_slot("user-1", "session-a", limit=15) as slot:
        slot.keep()

    redis_mock.zrem.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_turn_slot_releases_on_clean_exit_without_keep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forgetting ``slot.keep()`` on a clean exit releases the slot — the
    caller hasn't transferred ownership, so we must not leak it."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=1)
    redis_mock.zrem = AsyncMock(return_value=1)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    async with acquire_turn_slot("user-1", "session-a", limit=15):
        pass

    redis_mock.zrem.assert_called_once()


@pytest.mark.asyncio
async def test_acquire_turn_slot_raises_concurrent_limit_when_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=0)
    redis_mock.zrem = AsyncMock(return_value=0)
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    with pytest.raises(ConcurrentTurnLimitError):
        async with acquire_turn_slot("user-1", "session-a", limit=15):
            pytest.fail("body should not run when acquire fails")  # pragma: no cover

    # Reject path didn't acquire — must not release.
    redis_mock.zrem.assert_not_called()


@pytest.mark.asyncio
async def test_acquire_turn_slot_anonymous_user_skips_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``user_id`` falsy → no slot acquired, no Redis touched, no exception."""
    redis_mock = MagicMock()
    redis_mock.eval = AsyncMock(return_value=0)  # would reject if hit
    redis_mock.zrem = AsyncMock()
    monkeypatch.setattr(
        active_turns_module, "get_redis_async", AsyncMock(return_value=redis_mock)
    )

    async with acquire_turn_slot(None, "session-a", limit=15):
        pass

    redis_mock.eval.assert_not_called()
    redis_mock.zrem.assert_not_called()
