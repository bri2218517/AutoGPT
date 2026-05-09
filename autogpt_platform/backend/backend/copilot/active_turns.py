"""Per-user concurrent AutoPilot turn tracking.

Caps how many copilot chat turns a single user can have running
concurrently so a single API key cannot spawn hundreds of simultaneous
turns and exhaust shared infrastructure.

This module is the **domain wrapper** over the generic
:func:`backend.data.redis_helpers.try_acquire_concurrency_slot` primitive
— it supplies the per-user pool keying, the cap-from-Settings lookup,
the user-facing error message, and the
:func:`acquire_turn_slot` context manager that drives the slot's
admit / release / refresh lifecycle.

Public API
----------

* :func:`acquire_turn_slot` — async context manager every entry point
  (HTTP route, ``run_sub_session`` tool, ``AutoPilotBlock``) wraps around
  the create-session + enqueue dance. Raises
  :class:`ConcurrentTurnLimitError` on rejection.
* :func:`release_turn_slot` — invoked by ``mark_session_completed``
  when a turn ends, freeing the slot for the next admission.
* :func:`get_concurrent_turn_limit` /
  :func:`concurrent_turn_limit_message` — operator-tunable cap and the
  matching user-facing 429 detail.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.exceptions import RedisClusterException, RedisError

from backend.data.redis_client import get_redis_async
from backend.data.redis_helpers import SlotAdmission, try_acquire_concurrency_slot
from backend.util.settings import Settings

logger = logging.getLogger(__name__)


# Upper bound on a single AutoPilot turn's wall-clock duration. Beyond
# this we treat the turn as abandoned: the slot is reclaimed by the
# stale-cutoff sweep (so a crashed turn doesn't hold a slot forever) and
# the :class:`AutoPilotBlock` execution wait gives up. Far exceeds typical
# chat turn duration (seconds-minutes) so legitimate long-running tool
# calls (E2B sandbox, deep web crawls, etc.) aren't penalised. The normal
# release path is ``mark_session_completed``; this is the safety net.
MAX_TURN_LIFETIME_SECONDS = 6 * 60 * 60

_USER_ACTIVE_TURNS_KEY_PREFIX = "copilot:user_active_turns:"


def get_running_turn_limit() -> int:
    """Configured soft cap on concurrently *running* turns per user.

    Tasks submitted while the user is at this cap are queued (up to
    :func:`get_inflight_turn_limit`). Reading at call time so operators
    can retune via env-backed Settings without a redeploy.
    """
    return Settings().config.max_running_copilot_turns_per_user


def get_inflight_turn_limit() -> int:
    """Configured hard cap on in-flight (running + queued) turns per user.

    Once total in-flight hits this, :class:`InflightTurnLimitError` is
    raised on new submissions and the API returns HTTP 429.
    """
    return Settings().config.max_concurrent_copilot_turns_per_user


def inflight_turn_limit_message(limit: int | None = None) -> str:
    """User-facing 429 detail when the in-flight cap is hit. Includes
    queued tasks in the count to match the user's mental model
    ('15 active = 5 running + 10 queued')."""
    resolved = get_inflight_turn_limit() if limit is None else limit
    return (
        f"You've reached the limit of {resolved} active tasks (running + queued). "
        f"Please wait for one of your current tasks to finish before starting a new one."
    )


def running_turn_limit_message(limit: int | None = None) -> str:
    """Default :class:`ConcurrentTurnLimitError` detail when the
    *running* cap is hit on a path that does not queue (AutoPilotBlock,
    ``run_sub_session``). The HTTP route catches the error before it
    surfaces and replaces the message with the inflight one."""
    resolved = get_running_turn_limit() if limit is None else limit
    return (
        f"You have {resolved} AutoPilot tasks already running. "
        f"Please wait for one of them to finish before starting a new one."
    )


def queued_turn_message() -> str:
    """User-facing message rendered when a turn is queued instead of
    starting immediately because the running cap is full."""
    return (
        "Your task has been queued and will start automatically when one of "
        "your current tasks finishes."
    )


# Back-compat shims — older module name. Prefer the explicit running/inflight
# variants in new code.
get_concurrent_turn_limit = get_running_turn_limit
concurrent_turn_limit_message = running_turn_limit_message


class ConcurrentTurnLimitError(Exception):
    """User has reached the configured running AutoPilot turn cap.

    The HTTP chat route catches this and falls through to the FIFO
    queue (or 429 at the inflight cap). Non-HTTP paths surface the
    default ``running_turn_limit_message`` to the user.
    """

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or running_turn_limit_message())


def _user_pool_key(user_id: str) -> str:
    # Hash-tag braces ensure all keys for a single user co-locate on the
    # same Redis Cluster slot — required for any future Lua that touches
    # multiple per-user keys atomically.
    return f"{_USER_ACTIVE_TURNS_KEY_PREFIX}{{{user_id}}}"


async def _try_admit_user_turn(
    user_id: str, session_id: str, capacity: int
) -> SlotAdmission:
    """Atomic admit/refresh against the user's active-turn pool.

    Fails open (returns ``ADMITTED``) on Redis errors so a brown-out
    doesn't 429 every user — the cap is a safeguard, not a budget.
    """
    try:
        redis = await get_redis_async()
        now = time.time()
        return await try_acquire_concurrency_slot(
            redis,
            pool_key=_user_pool_key(user_id),
            slot_id=session_id,
            capacity=capacity,
            score=now,
            stale_before_score=now - MAX_TURN_LIFETIME_SECONDS,
            ttl_seconds=MAX_TURN_LIFETIME_SECONDS,
        )
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "concurrent-turn cap: Redis unavailable for user=%s; failing open: %s",
            user_id,
            exc,
        )
        return SlotAdmission.ADMITTED


async def get_running_session_ids(user_id: str) -> set[str]:
    """Set of session IDs currently consuming a running-turn slot.

    Used by the dispatcher to skip queued heads whose session already
    has a running turn — otherwise ``acquire_turn_slot`` returns
    ``REFRESHED`` and two turns share a single slot, with the first
    turn's completion releasing the shared slot prematurely.
    """
    try:
        redis = await get_redis_async()
        key = _user_pool_key(user_id)
        await redis.zremrangebyscore(
            key, "-inf", time.time() - MAX_TURN_LIFETIME_SECONDS
        )
        members = await redis.zrange(key, 0, -1)
        return {m.decode() if isinstance(m, bytes) else m for m in members}
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "get_running_session_ids: Redis unavailable for user=%s: %s", user_id, exc
        )
        return set()


async def count_running_turns(user_id: str) -> int:
    """Return the user's current running-turn count, after sweeping stale
    entries. Used by the queue layer to compute in-flight = running +
    queued for the hard cap. Best-effort — returns 0 if Redis is
    unreachable so the queue path stays available.
    """
    try:
        redis = await get_redis_async()
        key = _user_pool_key(user_id)
        await redis.zremrangebyscore(
            key, "-inf", time.time() - MAX_TURN_LIFETIME_SECONDS
        )
        return await redis.zcard(key)
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "count_running_turns: Redis unavailable for user=%s: %s", user_id, exc
        )
        return 0


async def release_turn_slot(user_id: str, session_id: str) -> None:
    """Free ``user_id``'s slot for ``session_id``. Idempotent.

    Best-effort — a Redis error only delays release until the next
    stale-cutoff sweep.
    """
    try:
        redis = await get_redis_async()
        await redis.zrem(_user_pool_key(user_id), session_id)
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "release_turn_slot: Redis unavailable for user=%s session=%s: %s",
            user_id,
            session_id,
            exc,
        )


class TurnSlot:
    """Handle yielded by :func:`acquire_turn_slot`.

    Call :meth:`keep` once a turn has been successfully scheduled to
    transfer ownership to ``mark_session_completed`` (the release path).
    Without ``keep``, the context manager auto-releases on exit — but
    only when *this* caller admitted the slot. A re-entrant refresh
    leaves the slot alone, since some earlier caller still owns it.
    """

    __slots__ = ("user_id", "session_id", "admitted", "_kept")

    def __init__(self, user_id: str, session_id: str) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.admitted = False
        self._kept = False

    def keep(self) -> None:
        """Transfer slot ownership out of this context. Caller is now
        responsible for ensuring ``mark_session_completed`` releases the
        slot (or accepts the stale-cutoff fallback)."""
        self._kept = True


@asynccontextmanager
async def acquire_turn_slot(
    user_id: str | None,
    session_id: str,
    capacity: int | None = None,
) -> AsyncIterator[TurnSlot]:
    """Reserve a turn slot for the duration of the ``async with`` block.

    ``capacity`` controls how many concurrent slots the user may hold:

    * The HTTP chat route uses the default (running cap, default 5) so
      the 6th submit raises :class:`ConcurrentTurnLimitError` and the
      route falls through to the FIFO queue.
    * Non-HTTP entry points (``schedule_turn`` for ``run_sub_session``
      / ``AutoPilotBlock``) pass the inflight cap (default 15) since
      they have no queue and must preserve the prior cap behaviour
      from #13064.

    Three branches on entry:

    * **Admitted** — fresh slot acquired; ``keep()`` transfers ownership
      to ``mark_session_completed``, otherwise the slot is released on
      exit.
    * **Refreshed** — same-``session_id`` re-entry (network retry,
      duplicate request); the existing slot's score is bumped but this
      caller does NOT own its release. Exiting without ``keep`` is a
      no-op.
    * **Rejected** — pool is at the configured cap; raises
      :class:`ConcurrentTurnLimitError` (caller maps to HTTP 429 or
      surfaces the message to the AutoPilot tool result).

    Anonymous sessions (``user_id`` falsy) bypass the gate entirely and
    yield a no-op handle.
    """
    handle = TurnSlot(user_id or "", session_id)
    if user_id:
        resolved_capacity = (
            capacity if capacity is not None else get_running_turn_limit()
        )
        outcome = await _try_admit_user_turn(user_id, session_id, resolved_capacity)
        if outcome is SlotAdmission.REJECTED:
            raise ConcurrentTurnLimitError(
                running_turn_limit_message(resolved_capacity)
            )
        if outcome is SlotAdmission.ADMITTED:
            handle.admitted = True

    try:
        yield handle
    finally:
        if handle.admitted and not handle._kept:
            await release_turn_slot(handle.user_id, handle.session_id)
