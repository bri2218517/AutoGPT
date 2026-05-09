"""Per-user concurrent AutoPilot turn tracking.

Tracks how many copilot chat turns a user has running concurrently and
enforces a hard cap so a single user (typically via the API) cannot spawn
hundreds of simultaneous turns and exhaust shared infrastructure.

Storage is a Redis sorted set per user (``copilot:user_active_turns:{user_id}``),
member = ``session_id`` (one in-flight turn per session at most), score =
unix timestamp of acquisition. Stale entries (older than ``stream_ttl``)
are auto-cleaned on every count, so a crashed turn that never released
its slot does not permanently consume the cap.

Acquisition is via a single Lua script that atomically:

* drops stale entries
* refreshes the score for an existing session_id (re-acquire is a no-op)
* otherwise checks the count against the limit and adds the new member

This keeps two concurrent ``POST /chat`` requests from both reading
``count = 14`` and both sneaking through.
"""

import logging
import time

from redis.exceptions import RedisClusterException, RedisError

from backend.copilot.config import ChatConfig
from backend.data.redis_client import AsyncRedisClient, get_redis_async

_config = ChatConfig()

logger = logging.getLogger(__name__)


# Default cap; can be overridden by the ``copilot_max_inflight_turns_per_user``
# setting once SECRT-2339 lands the configurable queue. For the hotfix this
# is the single in-flight gate.
MAX_CONCURRENT_TURNS_PER_USER = 15

CONCURRENT_TURN_LIMIT_MESSAGE = (
    f"You've reached the limit of {MAX_CONCURRENT_TURNS_PER_USER} active tasks. "
    f"Please wait for one of your current tasks to finish before starting a new one."
)

_USER_ACTIVE_TURNS_KEY_PREFIX = "copilot:user_active_turns:"


class ConcurrentTurnLimitError(Exception):
    """User has reached :data:`MAX_CONCURRENT_TURNS_PER_USER` in-flight
    AutoPilot turns. Maps to HTTP 429 in the API layer.
    """

    def __init__(self, message: str = CONCURRENT_TURN_LIMIT_MESSAGE) -> None:
        super().__init__(message)


# Atomic check-and-add. KEYS[1] = user's sorted set; ARGV[1] = session_id;
# ARGV[2] = now (score for new entry); ARGV[3] = stale cutoff timestamp;
# ARGV[4] = limit; ARGV[5] = TTL seconds. Returns 1 on acquired, 0 on rejected.
_TRY_ACQUIRE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[3])
local existing = redis.call('ZSCORE', KEYS[1], ARGV[1])
if existing then
    redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1])
    redis.call('EXPIRE', KEYS[1], ARGV[5])
    return 1
end
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[4]) then
    return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""


def _user_key(user_id: str) -> str:
    # Hash-tag braces ensure all keys for a single user co-locate on the same
    # Redis Cluster slot — required for any future Lua that touches multiple
    # per-user keys atomically.
    return f"{_USER_ACTIVE_TURNS_KEY_PREFIX}{{{user_id}}}"


async def try_acquire_turn_slot(
    user_id: str,
    session_id: str,
    limit: int = MAX_CONCURRENT_TURNS_PER_USER,
) -> bool:
    """Atomically reserve a turn slot for ``user_id``.

    Returns ``True`` if a slot was acquired (or the same ``session_id`` was
    already present and got its score refreshed), ``False`` if the user is at
    or above ``limit`` active turns.

    Fails open on Redis errors — the route continues but logs a warning.
    Failing closed here would 429 every user during a Redis brown-out, which
    is worse than the abuse-protection brief gap.
    """
    try:
        redis = await get_redis_async()
        now = time.time()
        stale_cutoff = now - _config.stream_ttl
        result = await redis.eval(  # type: ignore[misc]
            _TRY_ACQUIRE_SCRIPT,
            1,
            _user_key(user_id),
            session_id,
            str(now),
            str(stale_cutoff),
            str(limit),
            str(_config.stream_ttl),
        )
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "try_acquire_turn_slot: Redis unavailable for user=%s; failing open: %s",
            user_id,
            exc,
        )
        return True
    return int(result) == 1


async def release_turn_slot(user_id: str, session_id: str) -> None:
    """Remove ``session_id`` from ``user_id``'s active-turns set.

    Idempotent. Best-effort — a Redis error here only delays slot release
    until the stale-cutoff sweep on the next acquisition.
    """
    try:
        redis = await get_redis_async()
        await redis.zrem(_user_key(user_id), session_id)
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "release_turn_slot: Redis unavailable for user=%s session=%s: %s",
            user_id,
            session_id,
            exc,
        )


async def count_active_turns(user_id: str) -> int:
    """Return the user's current active-turn count, after sweeping stale
    entries. Best-effort — returns 0 if Redis is unreachable.
    """
    try:
        redis: AsyncRedisClient = await get_redis_async()
        key = _user_key(user_id)
        await redis.zremrangebyscore(key, "-inf", time.time() - _config.stream_ttl)
        return await redis.zcard(key)
    except (RedisError, RedisClusterException, ConnectionError, OSError) as exc:
        logger.warning(
            "count_active_turns: Redis unavailable for user=%s: %s", user_id, exc
        )
        return 0
