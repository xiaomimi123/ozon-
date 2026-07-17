"""WS 进度广播：后端可选（memory 本地 fan-out / redis pub/sub 跨进程）。

- memory（默认）：单进程内，publish 直接向已连接的 WebSocket fan-out（M1 起的行为，保持不变）。
- redis：worker 进程 publish 到 Redis 频道，API 进程订阅后再本地 fan-out 给 WS 连接，
  解决 ARQ worker 与 API 分属不同进程时进度广播不到 WS 的问题。
"""
import asyncio
import json

from fastapi import WebSocket

from app.core.config import settings

CHANNEL = "ws:progress"


class Broadcaster:
    def __init__(self):
        self._conns: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._redis = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._conns.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._conns.discard(ws)

    async def _local_broadcast(self, msg: dict):
        """本地 fan-out：向当前进程内所有已连接的 WS 推送消息。"""
        async with self._lock:
            conns = list(self._conns)
        for ws in conns:
            try:
                await ws.send_json(msg)
            except Exception:
                await self.disconnect(ws)

    async def _get_redis(self):
        """懒加载 redis 连接（仅 redis 后端会用到）。"""
        if self._redis is None:
            from redis.asyncio import from_url
            self._redis = from_url(settings.redis_url)
        return self._redis

    async def publish(self, msg: dict):
        """按 settings.progress_backend 路由：redis→发布到频道；memory→本地 fan-out。"""
        if settings.progress_backend == "redis":
            r = await self._get_redis()
            await r.publish(CHANNEL, json.dumps(msg))
        else:
            await self._local_broadcast(msg)

    async def start_redis_subscriber(self):
        """redis 后端专用：API 进程订阅频道，收到消息后本地 fan-out 给 WS 连接。"""
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") == "message":
                try:
                    await self._local_broadcast(json.loads(message["data"]))
                except Exception:
                    pass


broadcaster = Broadcaster()
