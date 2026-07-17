"""Broadcaster 后端可选（memory 本地 fan-out / redis pub/sub 跨进程）单测。"""
import pytest

from app.core.progress import Broadcaster


@pytest.mark.asyncio
async def test_memory_backend_local_broadcast(monkeypatch):
    """memory 后端（默认）：publish 直接本地 fan-out 到已连接的 WS。"""
    monkeypatch.setattr("app.core.config.settings.progress_backend", "memory", raising=False)
    b = Broadcaster()
    got = []

    class FakeWS:
        async def send_json(self, m):
            got.append(m)

    b._conns.add(FakeWS())
    await b.publish({"x": 1})
    assert got == [{"x": 1}]


@pytest.mark.asyncio
async def test_redis_backend_routes_to_redis(monkeypatch):
    """redis 后端：publish 走 redis.publish，不直接本地 fan-out（靠订阅端回来再广播）。"""
    monkeypatch.setattr("app.core.config.settings.progress_backend", "redis", raising=False)
    published = []

    class FakeRedis:
        async def publish(self, ch, data):
            published.append((ch, data))

    b = Broadcaster()
    b._redis = FakeRedis()
    local = []

    class FakeWS:
        async def send_json(self, m):
            local.append(m)

    b._conns.add(FakeWS())
    await b.publish({"y": 2})
    assert published and published[0][0] == "ws:progress"
    assert local == []
