"""内存 pub/sub 广播器：管理 WebSocket 连接并向所有在线连接推送采集进度。"""
import asyncio
from fastapi import WebSocket

class Broadcaster:
    def __init__(self):
        self._conns: set[WebSocket] = set()
        self._lock = asyncio.Lock()
    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._conns.add(ws)
    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._conns.discard(ws)
    async def publish(self, msg: dict):
        async with self._lock:
            conns = list(self._conns)
        for ws in conns:
            try:
                await ws.send_json(msg)
            except Exception:
                await self.disconnect(ws)

broadcaster = Broadcaster()
