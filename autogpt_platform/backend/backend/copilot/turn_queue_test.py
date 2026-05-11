"""Unit tests for turn_queue: per-user FIFO queue layered over ChatMessage.

DB access is mocked via the ``backend.copilot.turn_queue.chat_db``
indirection — same accessor pattern the executor subprocess uses to RPC
into ``DatabaseManager``. Patching the accessor avoids reaching for
Prisma directly while still exercising the queue's branching.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.copilot import turn_queue
from backend.copilot.model import ChatMessage as PydanticChatMessage


class _NoopAsyncCM:
    """Stand-in for the Redis NX session lock context manager. The lock
    only matters in production for cross-replica serialisation; in unit
    tests there's no concurrent submitter so we just no-op."""

    async def __aenter__(self):
        return True

    async def __aexit__(self, *exc):
        return None


def _pyd_message(**overrides) -> PydanticChatMessage:
    """Build a Pydantic ChatMessage with sensible defaults overrideable."""
    base = {
        "id": "msg-1",
        "role": "user",
        "content": "hello",
        "session_id": "s1",
        "chat_status": "queued",
        "metadata": None,
        "created_at": datetime.now(timezone.utc),
        "sequence": 1,
    }
    base.update(overrides)
    return PydanticChatMessage(**base)


# ── enqueue_turn payload encoding ──────────────────────────────────────


@pytest.mark.asyncio
async def test_enqueue_turn_packs_metadata_into_metadata_payload() -> None:
    """Non-message dispatch params (file_ids, mode, model, permissions,
    context, request_arrival_at) land in the ``metadata`` payload
    so the dispatcher can replay the original turn shape later."""
    db = MagicMock()
    db.get_next_sequence = AsyncMock(return_value=42)
    db.insert_chat_message = AsyncMock(return_value=_pyd_message(sequence=42))
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.model._get_session_lock",
            return_value=_NoopAsyncCM(),
        ),
        patch(
            "backend.copilot.model.invalidate_session_cache",
            new=AsyncMock(),
        ),
    ):
        await turn_queue.enqueue_turn(
            session_id="s1",
            message="hello",
            message_id="msg-1",
            context={"url": "https://example.com"},
            file_ids=["f1", "f2"],
            mode="extended_thinking",
            model="advanced",
            permissions={"tool_filter": "allow"},
            request_arrival_at=123.45,
        )
    kwargs = db.insert_chat_message.call_args.kwargs
    assert kwargs["session_id"] == "s1"
    assert kwargs["sequence"] == 42
    metadata = kwargs["metadata"]
    assert metadata["context"] == {"url": "https://example.com"}
    assert metadata["file_ids"] == ["f1", "f2"]
    assert metadata["mode"] == "extended_thinking"
    assert metadata["model"] == "advanced"
    assert metadata["permissions"] == {"tool_filter": "allow"}
    assert metadata["request_arrival_at"] == 123.45


@pytest.mark.asyncio
async def test_enqueue_turn_omits_null_fields_from_metadata() -> None:
    """A turn with no extra params (no file_ids / mode / context) leaves
    ``metadata`` NULL rather than an empty object — keeps the
    column tiny on the hot ChatMessage table."""
    db = MagicMock()
    db.get_next_sequence = AsyncMock(return_value=1)
    db.insert_chat_message = AsyncMock(return_value=_pyd_message())
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.model._get_session_lock",
            return_value=_NoopAsyncCM(),
        ),
        patch(
            "backend.copilot.model.invalidate_session_cache",
            new=AsyncMock(),
        ),
    ):
        await turn_queue.enqueue_turn(session_id="s1", message="hello")
    assert db.insert_chat_message.call_args.kwargs["metadata"] is None


# ── cancel_queued_turn ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_queued_turn_returns_true_and_invalidates_cache() -> None:
    """A successful cancel transitions ``chatStatus`` queued → cancelled
    and invalidates the session cache so the frontend drops the badge."""
    db = MagicMock()
    cancelled = _pyd_message(session_id="s1", chat_status="cancelled")
    db.transition_chat_message_status = AsyncMock(return_value=cancelled)
    invalidate = AsyncMock()
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch.object(turn_queue, "invalidate_session_cache", new=invalidate),
    ):
        ok = await turn_queue.cancel_queued_turn(user_id="u1", message_id="msg-1")
    assert ok is True
    invalidate.assert_awaited_once_with("s1")
    db.transition_chat_message_status.assert_awaited_once_with(
        message_id="msg-1",
        from_status="queued",
        to_status="cancelled",
        user_id="u1",
    )


@pytest.mark.asyncio
async def test_cancel_queued_turn_returns_false_when_not_owned_or_not_queued() -> None:
    db = MagicMock()
    db.transition_chat_message_status = AsyncMock(return_value=None)
    with patch.object(turn_queue, "chat_db", return_value=db):
        ok = await turn_queue.cancel_queued_turn(user_id="u1", message_id="msg-1")
    assert ok is False


# ── claim_queued_turn_by_id ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_claim_queued_turn_by_id_returns_none_when_no_longer_queued() -> None:
    """A parallel cancel / dispatch that flipped ``chatStatus`` away
    from ``"queued"`` before the claim's CAS matched any row → None,
    so the dispatcher doesn't promote a different unvalidated row."""
    db = MagicMock()
    db.transition_chat_message_status = AsyncMock(return_value=None)
    with patch.object(turn_queue, "chat_db", return_value=db):
        row = await turn_queue.claim_queued_turn_by_id("msg-1")
    assert row is None


@pytest.mark.asyncio
async def test_claim_queued_turn_by_id_returns_row_when_claimed() -> None:
    """When the claim wins the race, the dispatcher gets the row back."""
    claimed = _pyd_message(chat_status="idle")
    db = MagicMock()
    db.transition_chat_message_status = AsyncMock(return_value=claimed)
    with patch.object(turn_queue, "chat_db", return_value=db):
        row = await turn_queue.claim_queued_turn_by_id("msg-1")
    assert row is claimed
    db.transition_chat_message_status.assert_awaited_once_with(
        message_id="msg-1", from_status="queued", to_status="idle"
    )


# ── try_enqueue_turn ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_try_enqueue_turn_raises_when_at_inflight_cap() -> None:
    """Pre-check rejects when running + queued already equals the cap."""
    db = MagicMock()
    db.count_chat_messages_by_status = AsyncMock(return_value=10)
    db.insert_chat_message = AsyncMock()
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch.object(turn_queue, "count_running_turns", new=AsyncMock(return_value=5)),
    ):
        with pytest.raises(turn_queue.InflightCapExceeded):
            await turn_queue.try_enqueue_turn(
                user_id="u1",
                inflight_cap=15,
                session_id="s1",
                message="hi",
            )
    db.insert_chat_message.assert_not_awaited()


# ── dispatch_next_for_user gating ──────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_leaves_queued_when_user_paywalled() -> None:
    """A queued head whose owner has lapsed to NO_TIER stays queued —
    no DB write, no transition. The next slot-free tick re-validates;
    if the user re-subscribes the turn dispatches automatically."""
    head = _pyd_message()
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head])
    db.transition_chat_message_status = AsyncMock()
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is False
    db.transition_chat_message_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_returns_false_when_queue_empty() -> None:
    """No-op when there's nothing queued for the user."""
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[])
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is False


@pytest.mark.asyncio
async def test_dispatch_skips_busy_session_picks_next_idle() -> None:
    """Head-of-line tolerance: if the oldest queued row's session is busy,
    the dispatcher picks the first queued row whose session is idle.
    Per-session FIFO is preserved, cross-session ordering is loosened."""
    head = _pyd_message(id="msg-1", session_id="busy-session")
    next_idle = _pyd_message(id="msg-2", session_id="idle-session")
    claimed = _pyd_message(id="msg-2", session_id="idle-session", chat_status="idle")
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head, next_idle])
    db.transition_chat_message_status = AsyncMock(return_value=claimed)

    class _SlotCM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *exc):
            return None

    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "backend.copilot.rate_limit.get_global_rate_limits",
            new=AsyncMock(return_value=(100, 1000, None)),
        ),
        patch(
            "backend.copilot.rate_limit.check_rate_limit",
            new=AsyncMock(),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value={"busy-session"}),
        ),
        patch(
            "backend.copilot.active_turns.acquire_turn_slot",
            return_value=_SlotCM(),
        ),
        patch(
            "backend.copilot.executor.utils.dispatch_turn",
            new=AsyncMock(),
        ),
        patch.object(turn_queue, "invalidate_session_cache", new=AsyncMock()),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is True
    db.transition_chat_message_status.assert_awaited_once_with(
        message_id="msg-2", from_status="queued", to_status="idle"
    )


@pytest.mark.asyncio
async def test_dispatch_returns_false_when_all_sessions_busy() -> None:
    """If every queued row's session is busy, defer the whole dispatch."""
    queued = [
        _pyd_message(id="msg-1", session_id="busy-1"),
        _pyd_message(id="msg-2", session_id="busy-2"),
    ]
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=queued)
    db.transition_chat_message_status = AsyncMock()
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value={"busy-1", "busy-2"}),
        ),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is False
    db.transition_chat_message_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_leaves_queued_on_rate_limit_exceeded() -> None:
    """Rate-limit hit at dispatch time → row stays queued. The window
    will reset and the next slot-free tick promotes it automatically."""
    from backend.copilot.rate_limit import RateLimitExceeded

    head = _pyd_message()
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head])
    db.transition_chat_message_status = AsyncMock()
    resets_at = datetime.now(timezone.utc) + timedelta(hours=1)
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "backend.copilot.rate_limit.get_global_rate_limits",
            new=AsyncMock(return_value=(100, 1000, None)),
        ),
        patch(
            "backend.copilot.rate_limit.check_rate_limit",
            new=AsyncMock(side_effect=RateLimitExceeded("daily", resets_at)),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is False
    db.transition_chat_message_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_defers_on_rate_limit_unavailable() -> None:
    """Rate-limit service degraded → leave row queued for the next
    slot-free tick, no transition."""
    from backend.copilot.rate_limit import RateLimitUnavailable

    head = _pyd_message()
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head])
    db.transition_chat_message_status = AsyncMock()
    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "backend.copilot.rate_limit.get_global_rate_limits",
            new=AsyncMock(side_effect=RateLimitUnavailable()),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is False
    db.transition_chat_message_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispatch_happy_path_claims_and_dispatches() -> None:
    """All gates pass → claim the validated row by id, acquire the slot,
    dispatch_turn, invalidate session cache, return True."""
    head = _pyd_message(metadata={"mode": "extended_thinking"})
    claimed = _pyd_message(chat_status="idle", metadata={"mode": "extended_thinking"})
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head])
    db.transition_chat_message_status = AsyncMock(return_value=claimed)
    dispatch_turn_mock = AsyncMock()
    invalidate = AsyncMock()

    class _SlotCM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *exc):
            return None

    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "backend.copilot.rate_limit.get_global_rate_limits",
            new=AsyncMock(return_value=(100, 1000, None)),
        ),
        patch(
            "backend.copilot.rate_limit.check_rate_limit",
            new=AsyncMock(),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "backend.copilot.active_turns.acquire_turn_slot",
            return_value=_SlotCM(),
        ),
        patch(
            "backend.copilot.executor.utils.dispatch_turn",
            new=dispatch_turn_mock,
        ),
        patch.object(turn_queue, "invalidate_session_cache", new=invalidate),
    ):
        promoted = await turn_queue.dispatch_next_for_user("u1")
    assert promoted is True
    dispatch_turn_mock.assert_awaited_once()
    invalidate.assert_awaited_once_with("s1")
    # Only the claim transition fired — no restore.
    db.transition_chat_message_status.assert_awaited_once_with(
        message_id="msg-1", from_status="queued", to_status="idle"
    )


@pytest.mark.asyncio
async def test_dispatch_rolls_claim_back_on_dispatch_failure() -> None:
    """If dispatch_turn raises after the claim, the claim must be rolled
    back so the row can be re-promoted on the next slot-free tick."""
    head = _pyd_message()
    claimed = _pyd_message(chat_status="idle")
    db = MagicMock()
    db.list_chat_messages_by_status = AsyncMock(return_value=[head])
    # First call (claim) returns the claimed row; second call (restore)
    # is the rollback after dispatch failure.
    db.transition_chat_message_status = AsyncMock(side_effect=[claimed, None])
    dispatch_turn_mock = AsyncMock(side_effect=RuntimeError("RabbitMQ blip"))

    class _SlotCM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *exc):
            return None

    with (
        patch.object(turn_queue, "chat_db", return_value=db),
        patch(
            "backend.copilot.rate_limit.is_user_paywalled",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "backend.copilot.rate_limit.get_global_rate_limits",
            new=AsyncMock(return_value=(100, 1000, None)),
        ),
        patch(
            "backend.copilot.rate_limit.check_rate_limit",
            new=AsyncMock(),
        ),
        patch(
            "backend.copilot.active_turns.get_running_session_ids",
            new=AsyncMock(return_value=set()),
        ),
        patch(
            "backend.copilot.active_turns.acquire_turn_slot",
            return_value=_SlotCM(),
        ),
        patch(
            "backend.copilot.executor.utils.dispatch_turn",
            new=dispatch_turn_mock,
        ),
        patch.object(turn_queue, "invalidate_session_cache", new=AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="RabbitMQ blip"):
            await turn_queue.dispatch_next_for_user("u1")
    # Two transitions: claim then restore.
    assert db.transition_chat_message_status.await_count == 2
    db.transition_chat_message_status.assert_any_await(
        message_id="msg-1", from_status="queued", to_status="idle"
    )
    db.transition_chat_message_status.assert_any_await(
        message_id="msg-1", from_status="idle", to_status="queued"
    )


# ── status constants pinned ────────────────────────────────────────────
