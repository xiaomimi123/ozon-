"""节奏配置 API schema。"""
from pydantic import BaseModel

class PaceIn(BaseModel):
    min_interval_sec: int = 60
    max_interval_sec: int = 180
    daily_limit: int = 200
    active_hours: list[int] = [9, 23]
    wait_ozon_approval: bool = True

class PaceOut(PaceIn):
    task_id: int | None = None
