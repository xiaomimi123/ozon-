"""外部生图产物落盘：字节 → static_dir，内容 hash 命名（确定性），返回 /static/images/ 相对 URL。"""
import hashlib
import os


def save_image_bytes(raw: bytes, static_dir: str, *, prefix: str = "gen") -> str:
    os.makedirs(static_dir, exist_ok=True)
    h = hashlib.sha1(raw).hexdigest()[:12]
    fname = f"{prefix}_{h}.png"
    with open(os.path.join(static_dir, fname), "wb") as f:
        f.write(raw)
    return f"/static/images/{fname}"
