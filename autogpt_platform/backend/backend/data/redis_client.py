import logging
import os
from typing import Union

from dotenv import load_dotenv
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.cluster import RedisCluster as AsyncRedisCluster
from redis.cluster import ClusterNode, RedisCluster

from backend.util.cache import cached, thread_cached
from backend.util.retry import conn_retry

load_dotenv()

HOST = os.getenv("REDIS_HOST", "localhost")
PORT = int(os.getenv("REDIS_PORT", "6379"))
PASSWORD = os.getenv("REDIS_PASSWORD", None)

# When true, connect via Redis Cluster client. The single HOST/PORT is used as
# a startup node — the cluster client auto-discovers the rest via CLUSTER SLOTS.
# Keep this off by default so the standalone deployment path is unchanged.
CLUSTER_ENABLED = os.getenv("REDIS_CLUSTER_ENABLED", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Default socket timeouts so a wedged Redis endpoint can't hang callers
# indefinitely — long-running code paths (cluster_lock refresh in particular)
# rely on these to fail-fast instead of blocking on no-response TCP. Override
# via env if a specific deployment needs a different budget.
#
# 30s matches the convention in ``backend.data.rabbitmq`` and leaves ~6x
# headroom over the largest ``xread(block=5000)`` wait in stream_registry.
# The connect timeout is shorter (5s) because initial connects should be
# fast; a slow connect usually means the endpoint is genuinely unreachable.
SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))
SOCKET_CONNECT_TIMEOUT = float(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "5"))
# How often redis-py sends a PING on idle connections to detect half-open
# sockets; cheap and avoids waiting for the OS TCP keepalive (~2h default).
HEALTH_CHECK_INTERVAL = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))

logger = logging.getLogger(__name__)

# Type aliases so callers keep a single name for the client regardless of
# whether we're in standalone or cluster mode. Both clients expose the
# single-key command surface we rely on (GET/SET/INCR/EXPIRE, streams,
# pipelines on a single slot, EVAL on a single key).
RedisClient = Union[Redis, RedisCluster]
AsyncRedisClient = Union[AsyncRedis, AsyncRedisCluster]


@conn_retry("Redis", "Acquiring connection")
def connect() -> RedisClient:
    if CLUSTER_ENABLED:
        c: RedisClient = RedisCluster(
            startup_nodes=[ClusterNode(HOST, PORT)],
            password=PASSWORD,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
        )
    else:
        c = Redis(
            host=HOST,
            port=PORT,
            password=PASSWORD,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
        )
    c.ping()
    return c


@conn_retry("Redis", "Releasing connection")
def disconnect():
    get_redis().close()


@cached(ttl_seconds=3600)
def get_redis() -> RedisClient:
    return connect()


@conn_retry("AsyncRedis", "Acquiring connection")
async def connect_async() -> AsyncRedisClient:
    if CLUSTER_ENABLED:
        c: AsyncRedisClient = AsyncRedisCluster(
            host=HOST,
            port=PORT,
            password=PASSWORD,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
        )
    else:
        c = AsyncRedis(
            host=HOST,
            port=PORT,
            password=PASSWORD,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT,
            socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
            socket_keepalive=True,
            health_check_interval=HEALTH_CHECK_INTERVAL,
        )
    await c.ping()
    return c


@conn_retry("AsyncRedis", "Releasing connection")
async def disconnect_async():
    c = await get_redis_async()
    await c.close()


@thread_cached
async def get_redis_async() -> AsyncRedisClient:
    return await connect_async()


# ---------------------------------------------------------------------------
# Pub/sub connections
#
# redis-py's async RedisCluster does not expose ``pubsub()`` at all (only the
# sync client does).  Classic (non-sharded) pub/sub in a Redis Cluster is
# already broadcast across every node — any ``PUBLISH`` on any node fans out
# to every subscriber regardless of which node they connected to — so we can
# safely use a plain ``AsyncRedis`` / ``Redis`` connection to the seed node
# for pub/sub alone.  Callers use ``get_redis_pubsub_*`` instead of the
# cluster-aware client for SUBSCRIBE/PUBLISH only; all other commands keep
# going through the cluster-aware singleton.
#
# In standalone mode these helpers return the same singleton as
# ``get_redis`` / ``get_redis_async``, so non-cluster deployments are
# unaffected.
# ---------------------------------------------------------------------------


@conn_retry("RedisPubSub", "Acquiring connection")
def connect_pubsub() -> Redis:
    c = Redis(
        host=HOST,
        port=PORT,
        password=PASSWORD,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT,
        socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
        socket_keepalive=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
    )
    c.ping()
    return c


@conn_retry("AsyncRedisPubSub", "Acquiring connection")
async def connect_pubsub_async() -> AsyncRedis:
    c = AsyncRedis(
        host=HOST,
        port=PORT,
        password=PASSWORD,
        decode_responses=True,
        socket_timeout=SOCKET_TIMEOUT,
        socket_connect_timeout=SOCKET_CONNECT_TIMEOUT,
        socket_keepalive=True,
        health_check_interval=HEALTH_CHECK_INTERVAL,
    )
    await c.ping()
    return c


@cached(ttl_seconds=3600)
def get_redis_pubsub() -> Redis:
    """Return a standalone ``Redis`` client suitable for pub/sub.

    In cluster mode this is a plain connection to the seed node (cluster
    pub/sub is broadcast, so one-node connection is fine).  In standalone
    mode this is the same underlying endpoint as ``get_redis()`` — we build
    a dedicated connection so pub/sub long-polls do not share a socket with
    the regular command traffic and stall it.
    """
    return connect_pubsub()


@thread_cached
async def get_redis_pubsub_async() -> AsyncRedis:
    """Async equivalent of :func:`get_redis_pubsub`.

    Separate connection for the same reason as the sync helper: a
    subscribed connection blocks on ``listen()`` and cannot be interleaved
    with regular commands.
    """
    return await connect_pubsub_async()
