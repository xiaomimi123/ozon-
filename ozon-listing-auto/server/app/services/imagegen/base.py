"""改图 provider 抽象：统一 process(op) 接口（§5.5.5）。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol

LOCAL_OPS = {"rmbg", "whitebg", "watermark", "crop_norm"}   # 本地可处理
GEN_OPS = {"gen"}                                           # 需外部生图 provider


@dataclass
class ImageResult:
    url: str                       # 产物相对 URL（/static/images/xxx.png）或文件名
    provider: str
    meta: dict = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str
    async def process(self, *, image: bytes, op: str, params: dict) -> ImageResult: ...
