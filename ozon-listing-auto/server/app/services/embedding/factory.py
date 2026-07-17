"""按名返回 Embedder；默认 mock，clip 惰性 import。"""
from app.services.embedding.base import Embedder
from app.services.embedding.mock import MockEmbedder

def get_embedder(name: str = "mock") -> Embedder:
    if name == "mock":
        return MockEmbedder()
    if name == "clip":
        from app.services.embedding.clip import ChineseClipEmbedder
        return ChineseClipEmbedder()
    raise ValueError(f"未知 embedder: {name}")
