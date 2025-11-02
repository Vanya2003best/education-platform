"""Regression tests for the Redis cache manager."""

import sys
from pathlib import Path

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.utils.cache import CacheManager  # noqa: E402  pylint: disable=wrong-import-position


class DummyRedisClient:
    """Fake Redis client that simulates connection issues."""

    def __init__(self, exception: Exception):
        self._exception = exception
        self.closed = False

    async def ping(self):  # pragma: no cover - exercised in tests
        raise self._exception

    async def close(self):  # pragma: no cover - exercised in tests
        self.closed = True


@pytest.fixture
def anyio_backend():
    """Force anyio to execute tests on the asyncio backend only."""

    return "asyncio"


@pytest.mark.anyio
async def test_connect_gracefully_handles_connection_errors(monkeypatch, caplog):
    """Connection failures should disable caching without error logs."""

    manager = CacheManager()
    fake_client = DummyRedisClient(RedisConnectionError("connection refused"))

    monkeypatch.setattr(manager, "_build_client", lambda: fake_client)

    caplog.set_level("WARNING")

    await manager.connect()

    assert not manager.is_connected()
    assert manager.redis_client is None
    assert fake_client.closed
    assert any("Redis unavailable" in record.message for record in caplog.records)
