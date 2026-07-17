"""采集进度 WebSocket 端点。"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core.progress import broadcaster

router = APIRouter()

@router.websocket("/ws/progress")
async def ws_progress(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            await ws.receive_text()   # 保活；客户端可发心跳
    except WebSocketDisconnect:
        await broadcaster.disconnect(ws)
