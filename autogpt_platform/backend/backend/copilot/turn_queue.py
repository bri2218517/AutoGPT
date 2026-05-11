"""Per-user FIFO queue for AutoPilot chat turns that exceeded the soft
running cap.

Storage is the existing :class:`prisma.models.ChatMessage` table with
a ``chatStatus`` text enum capturing the row's queue lifecycle:

* ``"idle"``      — DEFAULT, normal row (history or immediately dispatched)
* ``"queued"``    — user row waiting for a running slot
* ``"cancelled"`` — user dropped the queued row before promotion (terminal)

State transitions:

* (insert)     → ``"queued"`` via ``enqueue_turn``
* ``"queued"`` → ``"idle"`` via ``claim_queued_turn_by_id`` (dispatcher)
* ``"queued"`` → ``"cancelled"`` via ``cancel_queued_turn`` (user)
* ``"idle"``   → ``"queued"`` via dispatch-failure restore path

Cancelled rows stay in the conversation as orphan user bubbles — the
frontend renders a "Cancelled" indicator from ``chat_status`` so the
user can tell what happened.

Per-session "is a turn running?" is tracked separately on
``ChatSession.currentTurnStartedAt`` and drives the per-user soft cap.
We don't duplicate that signal onto ChatMessage rows.

If the dispatcher finds the user paywalled / rate-limited at promote
time, the row stays ``"queued"`` and the next slot-free hook re-validates
— the row gets dispatched once eligibility returns, or the user cancels
manually.

Layered on top of:

* :mod:`backend.copilot.active_turns` — Postgres-backed running-turn
  tracker (one ``ChatSession.currentTurnStartedAt`` per session).
* :mod:`backend.copilot.executor.utils` — :func:`schedule_chat_turn`
  is the same primitive the HTTP route uses for an immediate dispatch;
  the dispatcher reuses it so queued + immediate dispatches share one
  code path.

DB access goes through :func:`backend.data.db_accessors.chat_db` so
the dispatcher works from both the HTTP server (Prisma directly) and
the copilot_executor process (RPC via DatabaseManager) — the executor
is the hot caller because it runs ``mark_session_completed`` which
fires the slot-free dispatch.

Caps are configured via:

* :func:`backend.copilot.active_turns.get_running_turn_limit`   (soft / 5)
* :func:`backend.copilot.active_turns.get_inflight_turn_limit`  (hard / 15)
"""

import logging
import uuid
from typing import Any, Mapping

from backend.copilot.active_turns import count_running_turns
from backend.copilot.model import (
    CHAT_STATUS_CANCELLED,
    CHAT_STATUS_IDLE,
    CHAT_STATUS_QUEUED,
    ChatMessage,
    _get_session_lock,
    invalidate_session_cache,
)
from backend.data.db_accessors import chat_db

logger = logging.getLogger(__name__)


async def count_queued_turns(user_id: str) -> int:
    """Number of ``chatStatus='queued'`` ChatMessage rows for ``user_id``."""
    return await chat_db().count_chat_messages_by_status(
        user_id=user_id, status=CHAT_STATUS_QUEUED
    )


async def count_inflight_turns(user_id: str) -> int:
    """Running + queued. Hard cap is enforced against this.

    Counts queued first then running so a concurrent queued→running
    promotion between the two reads can be double-counted (safe — caller
    rejects one extra task) but never missed. The cap may briefly read
    high under burst load, never low.
    """
    queued = await count_queued_turns(user_id)
    running = await count_running_turns(user_id)
    return queued + running


async def list_queued_turns(user_id: str) -> list[ChatMessage]:
    """User's queued tasks, oldest-first (FIFO order). UX surface for the
    'your queued tasks' panel."""
    return await chat_db().list_chat_messages_by_status(
        user_id=user_id, status=CHAT_STATUS_QUEUED
    )


class InflightCapExceeded(Exception):
    """User's running + queued total has reached the configured hard cap.

    Raised by :func:`try_enqueue_turn` so the route can map to HTTP 429.
    """


async def try_enqueue_turn(
    *,
    user_id: str,
    inflight_cap: int,
    session_id: str,
    message: str,
    message_id: str | None = None,
    is_user_message: bool = True,
    context: Mapping[str, str] | None = None,
    file_ids: list[str] | None = None,
    mode: str | None = None,
    model: str | None = None,
    permissions: Mapping[str, Any] | None = None,
    request_arrival_at: float = 0.0,
) -> ChatMessage:
    """Admit a queued turn against the user's hard cap.

    Non-locked count-then-insert: under burst, two concurrent submits
    can both pass the count and both insert, leaving the user briefly
    one or two over the cap. Same trade-off the graph-execution credit
    rate-limit accepts on its INCRBY path; the cap is a safeguard, not
    a budget.
    """
    if await count_inflight_turns(user_id) >= inflight_cap:
        raise InflightCapExceeded()
    return await enqueue_turn(
        session_id=session_id,
        message=message,
        message_id=message_id,
        is_user_message=is_user_message,
        context=context,
        file_ids=file_ids,
        mode=mode,
        model=model,
        permissions=permissions,
        request_arrival_at=request_arrival_at,
    )


async def enqueue_turn(
    *,
    session_id: str,
    message: str,
    message_id: str | None = None,
    is_user_message: bool = True,
    context: Mapping[str, str] | None = None,
    file_ids: list[str] | None = None,
    mode: str | None = None,
    model: str | None = None,
    permissions: Mapping[str, Any] | None = None,
    request_arrival_at: float = 0.0,
) -> ChatMessage:
    """Persist a user message that couldn't dispatch immediately because
    the user is at the running cap. Caller is responsible for the
    in-flight cap check AND session-ownership check upstream — once the
    row is committed the dispatcher owns it.

    The row is a regular ChatMessage (with ``role='user'``) plus the
    queue lifecycle columns. When the dispatcher claims it the queue
    columns are cleared and the row becomes an ordinary
    chat-conversation message.
    """
    metadata: dict[str, Any] = {}
    if context is not None:
        metadata["context"] = dict(context)
    if file_ids is not None:
        metadata["file_ids"] = list(file_ids)
    if mode is not None:
        metadata["mode"] = mode
    if model is not None:
        metadata["model"] = model
    if permissions is not None:
        metadata["permissions"] = dict(permissions)
    if request_arrival_at:
        metadata["request_arrival_at"] = request_arrival_at

    # The Redis NX session lock serialises with ``append_and_save_message``
    # so two concurrent submits to the same session can't pick the same
    # ``sequence`` and PK-collide on ``(sessionId, sequence)``. The caller's
    # ``get_next_sequence`` was an optimistic read; re-fetch inside the
    # lock so the authoritative value is whatever the lock holder sees now.
    db = chat_db()
    async with _get_session_lock(session_id):
        live_sequence = await db.get_next_sequence(session_id)
        row = await db.insert_chat_message(
            message_id=message_id or str(uuid.uuid4()),
            session_id=session_id,
            role="user" if is_user_message else "assistant",
            content=message,
            sequence=live_sequence,
            chat_status=CHAT_STATUS_QUEUED,
            metadata=metadata or None,
        )
    # The chat-session cache holds the message list; invalidate so the
    # next /chat read picks up the queued row (frontend renders a
    # 'Queued' badge based on ``chatStatus``).
    await invalidate_session_cache(session_id)
    return row


async def cancel_queued_turn(*, user_id: str, message_id: str) -> bool:
    """Mark a queued row as cancelled (``chatStatus`` ``"queued"`` →
    ``"cancelled"``). Returns True iff the CAS matched AND the row is
    owned by the user (via session).  Cancel/dispatch races resolve in
    a single atomic update.

    Invalidates the session cache on success so the frontend stops
    rendering the 'Queued' badge on its next refetch.
    """
    row = await chat_db().transition_chat_message_status(
        message_id=message_id,
        from_status=CHAT_STATUS_QUEUED,
        to_status=CHAT_STATUS_CANCELLED,
        user_id=user_id,
    )
    if row is None or row.session_id is None:
        return False
    await invalidate_session_cache(row.session_id)
    return True


async def claim_queued_turn_by_id(message_id: str) -> ChatMessage | None:
    """Atomically claim the queued row identified by ``message_id`` by
    transitioning ``chatStatus`` ``"queued"`` → ``"idle"``.  Returns
    the claimed row, or ``None`` if it was cancelled / already claimed
    by a concurrent dispatcher between the gate check and this call.

    The caller passes the exact ``message_id`` they validated (paywall,
    rate-limit) so a parallel cancel of the validated head doesn't
    silently promote a *different* — unvalidated — queued row.
    """
    return await chat_db().transition_chat_message_status(
        message_id=message_id,
        from_status=CHAT_STATUS_QUEUED,
        to_status=CHAT_STATUS_IDLE,
    )


async def dispatch_next_for_user(user_id: str) -> bool:
    """Promote at most one queued row for ``user_id`` from queued →
    running. Called when a running turn ends (slot frees) and on a
    routine timer to recover from missed dispatch events.

    Returns ``True`` iff a row was actually promoted.

    Pre-start re-validation runs *before* claiming the row so a
    paywalled user's queue head stays queued (rather than consuming a
    running slot for a turn that would immediately 402).  The row will
    auto-recover on the next dispatch tick once eligibility returns,
    or the user can cancel manually.
    """
    # Local imports to keep the cold-start path light and avoid pulling
    # the rate-limit + executor pipeline into modules that just want
    # queue counts.
    from backend.copilot.active_turns import acquire_turn_slot, get_running_session_ids
    from backend.copilot.config import ChatConfig
    from backend.copilot.executor.utils import dispatch_turn
    from backend.copilot.rate_limit import (
        RateLimitExceeded,
        RateLimitUnavailable,
        check_rate_limit,
        get_global_rate_limits,
        is_user_paywalled,
    )

    # Find the oldest queued row whose session is currently idle. Strict
    # FIFO across the whole queue would head-of-line block: if the
    # oldest queued turn targets a session that already has a running
    # turn, every subsequent queued task would stall behind it even
    # though they target idle sessions. So we iterate the queue and
    # pick the first row whose session isn't busy. Per-session FIFO is
    # preserved (oldest-first within each session); only cross-session
    # ordering is loosened, which matches the intent — sessions are
    # independent conversation contexts.
    busy_sessions = await get_running_session_ids(user_id)
    queued = await chat_db().list_chat_messages_by_status(
        user_id=user_id, status=CHAT_STATUS_QUEUED
    )
    head_id: str | None = None
    head_session_id: str | None = None
    for r in queued:
        if r.id and r.session_id and r.session_id not in busy_sessions:
            head_id = r.id
            head_session_id = r.session_id
            break
    if head_id is None or head_session_id is None:
        return False

    if await is_user_paywalled(user_id):
        # Mid-queue paywall lapse: leave the row queued. The next
        # slot-free hook re-validates; if the user re-subscribes the
        # turn dispatches automatically, otherwise they cancel manually.
        logger.info(
            "dispatch_next_for_user: user=%s paywalled, leaving message=%s queued",
            user_id,
            head_id,
        )
        return False

    cfg = ChatConfig()
    try:
        daily_limit, weekly_limit, _ = await get_global_rate_limits(
            user_id,
            cfg.daily_cost_limit_microdollars,
            cfg.weekly_cost_limit_microdollars,
        )
        await check_rate_limit(
            user_id=user_id,
            daily_cost_limit=daily_limit,
            weekly_cost_limit=weekly_limit,
        )
    except RateLimitExceeded as exc:
        # Same recovery model as paywall: leave the row queued, the
        # rate-limit window will reset and the next tick promotes it.
        logger.info(
            "dispatch_next_for_user: user=%s rate-limited (%s), leaving message=%s queued",
            user_id,
            exc,
            head_id,
        )
        return False
    except RateLimitUnavailable:
        logger.warning(
            "dispatch_next_for_user: rate-limit service degraded for user=%s; "
            "leaving queue intact for the next tick",
            user_id,
        )
        return False

    # Claim by the validated head's id specifically: a parallel cancel
    # between validation and claim must reject this dispatch, not promote
    # a *different* (unvalidated) row that happens to be next in the
    # queue.
    row = await claim_queued_turn_by_id(head_id)
    if row is None or row.id is None or row.session_id is None:
        # Head was cancelled or claimed by a concurrent dispatcher.
        # The next slot-free event will fire this again anyway.
        return False

    metadata = row.metadata or {}
    turn_id = str(uuid.uuid4())
    try:
        # The user's message is already persisted in ``ChatMessage``
        # from ``enqueue_turn``; the dispatcher must NOT route through
        # ``schedule_chat_turn``, which would re-save the row, hit the
        # PK-collision dedup, return None, and silently drop the
        # dispatch. Acquire the running slot ourselves and go straight
        # to the create-session + enqueue layer.
        async with acquire_turn_slot(user_id, row.session_id) as slot:
            await dispatch_turn(
                slot,
                session_id=row.session_id,
                user_id=user_id,
                turn_id=turn_id,
                message=row.content or "",
                is_user_message=row.role == "user",
                context=metadata.get("context"),
                file_ids=metadata.get("file_ids"),
                mode=metadata.get("mode"),
                model=metadata.get("model"),
                permissions=metadata.get("permissions"),
                request_arrival_at=float(metadata.get("request_arrival_at") or 0.0),
            )
    except Exception:
        # Roll the claim back so a missed-dispatch tick or the next
        # slot-free event can retry. The restore call has its own
        # try/except so a transient DB error there doesn't swallow the
        # original dispatch exception or leave the operator with no
        # signal — at minimum we log loudly so the orphaned row is
        # recoverable from logs + DB inspection.
        try:
            await chat_db().transition_chat_message_status(
                message_id=row.id,
                from_status=CHAT_STATUS_IDLE,
                to_status=CHAT_STATUS_QUEUED,
            )
        except Exception as restore_exc:
            logger.error(
                "dispatch_next_for_user: failed to restore claim for "
                "message=%s session=%s after dispatch failure; row left "
                "with chatStatus='idle' and will need manual recovery: %s",
                row.id,
                row.session_id,
                restore_exc,
            )
        raise
    # The promoted row's chatStatus was cleared to 'idle' by the claim;
    # refresh the chat-session cache so the frontend stops rendering
    # the 'Queued' badge for this message.
    await invalidate_session_cache(row.session_id)
    return True
