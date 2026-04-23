"""Unit tests for the env-gated dual Redis/Cluster client in ``redis_client``.

These tests avoid touching a real Redis by patching the constructors and
the ``ping()`` call.  They verify:

* When ``REDIS_CLUSTER_ENABLED`` is off, ``connect()`` / ``connect_async()``
  build a standalone ``Redis`` / ``AsyncRedis`` client.
* When the flag is on, they build ``RedisCluster`` / ``AsyncRedisCluster``
  instead, passing the same host/port/password/timeouts through.
"""

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio.cluster import RedisCluster as AsyncRedisCluster
from redis.cluster import RedisCluster

import backend.data.redis_client as redis_client


@pytest.fixture(autouse=True)
def _reset_module_caches() -> None:
    """Flush cached singletons between tests so the flag toggle is observed."""
    redis_client.get_redis.cache_clear()  # type: ignore[attr-defined]
    # thread_cached uses a per-thread dict keyed on the wrapped function.
    try:
        redis_client.get_redis_async.cache_clear()  # type: ignore[attr-defined]
    except AttributeError:
        pass


def _reload_with_flag(enabled: bool) -> SimpleNamespace:
    """Re-import the module with REDIS_CLUSTER_ENABLED set to *enabled*.

    Returns a namespace with the freshly imported module so callers can
    reach into its module-level globals.
    """
    with patch.dict(
        "os.environ", {"REDIS_CLUSTER_ENABLED": "true" if enabled else "false"}
    ):
        mod = importlib.reload(redis_client)
    return SimpleNamespace(mod=mod)


def test_connect_returns_standalone_when_flag_off() -> None:
    ns = _reload_with_flag(False)
    assert ns.mod.CLUSTER_ENABLED is False

    with (
        patch.object(ns.mod, "Redis", autospec=True) as mock_redis,
        patch.object(ns.mod, "RedisCluster", autospec=True) as mock_cluster,
    ):
        mock_redis.return_value = MagicMock(spec=Redis)
        client = ns.mod.connect()

    mock_redis.assert_called_once()
    mock_cluster.assert_not_called()
    client.ping.assert_called_once()


def test_connect_returns_cluster_when_flag_on() -> None:
    ns = _reload_with_flag(True)
    assert ns.mod.CLUSTER_ENABLED is True

    with (
        patch.object(ns.mod, "Redis", autospec=True) as mock_redis,
        patch.object(ns.mod, "RedisCluster", autospec=True) as mock_cluster,
    ):
        mock_cluster.return_value = MagicMock(spec=RedisCluster)
        client = ns.mod.connect()

    mock_cluster.assert_called_once()
    mock_redis.assert_not_called()
    kwargs = mock_cluster.call_args.kwargs
    # The startup node carries the configured host/port.
    assert kwargs["password"] == ns.mod.PASSWORD
    assert kwargs["decode_responses"] is True
    assert kwargs["socket_timeout"] == ns.mod.SOCKET_TIMEOUT
    assert kwargs["socket_connect_timeout"] == ns.mod.SOCKET_CONNECT_TIMEOUT
    assert kwargs["socket_keepalive"] is True
    assert kwargs["health_check_interval"] == ns.mod.HEALTH_CHECK_INTERVAL
    startup = kwargs["startup_nodes"]
    assert len(startup) == 1
    # ClusterNode resolves "localhost" → "127.0.0.1" internally; both are
    # valid representations of the configured host.
    assert startup[0].host in {ns.mod.HOST, "127.0.0.1"}
    assert startup[0].port == ns.mod.PORT
    client.ping.assert_called_once()


@pytest.mark.asyncio
async def test_connect_async_returns_standalone_when_flag_off() -> None:
    ns = _reload_with_flag(False)

    with (
        patch.object(ns.mod, "AsyncRedis", autospec=True) as mock_async,
        patch.object(ns.mod, "AsyncRedisCluster", autospec=True) as mock_cluster,
    ):
        fake = MagicMock(spec=AsyncRedis)
        fake.ping = AsyncMock()
        mock_async.return_value = fake
        client = await ns.mod.connect_async()

    mock_async.assert_called_once()
    mock_cluster.assert_not_called()
    client.ping.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_async_returns_cluster_when_flag_on() -> None:
    ns = _reload_with_flag(True)

    with (
        patch.object(ns.mod, "AsyncRedis", autospec=True) as mock_async,
        patch.object(ns.mod, "AsyncRedisCluster", autospec=True) as mock_cluster,
    ):
        fake = MagicMock(spec=AsyncRedisCluster)
        fake.ping = AsyncMock()
        mock_cluster.return_value = fake
        client = await ns.mod.connect_async()

    mock_cluster.assert_called_once()
    mock_async.assert_not_called()
    kwargs = mock_cluster.call_args.kwargs
    assert kwargs["host"] == ns.mod.HOST
    assert kwargs["port"] == ns.mod.PORT
    assert kwargs["password"] == ns.mod.PASSWORD
    assert kwargs["decode_responses"] is True
    client.ping.assert_awaited_once()


def test_flag_parser_accepts_common_truthy_values() -> None:
    for val in ("true", "TRUE", "1", "yes", "Yes"):
        ns = _reload_with_flag(False)
        with patch.dict("os.environ", {"REDIS_CLUSTER_ENABLED": val}):
            mod = importlib.reload(ns.mod)
            assert mod.CLUSTER_ENABLED is True, f"expected {val!r} to be truthy"
    # Clean up by reloading with flag off for any downstream tests.
    _reload_with_flag(False)
