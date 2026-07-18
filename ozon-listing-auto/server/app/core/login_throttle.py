"""登录失败限流（§3.2）：滑动窗口计失败次数 + 锁定窗口。内存实现, now 可注入供测试。
多 api 实例不共享计数（单实例够用；横向扩容改 Redis, 后置, 同 progress_backend 范式）。"""
from datetime import datetime, timedelta
from app.core.config import settings


class LoginThrottle:
    def __init__(self, max_attempts: int = 5, window_sec: int = 300, lockout_sec: int = 900):
        self.max_attempts = max_attempts
        self.window = timedelta(seconds=window_sec)
        self.lockout = timedelta(seconds=lockout_sec)
        self._fails: dict[str, list[datetime]] = {}   # key -> 窗口内失败时刻
        self._locked: dict[str, datetime] = {}        # key -> 锁定截止时刻

    def check(self, key: str, *, now: datetime) -> int | None:
        """锁定中返回剩余秒数(>0)，否则 None（顺带清理过期锁定）。"""
        until = self._locked.get(key)
        if until is not None:
            if now < until:
                return int((until - now).total_seconds()) + 1
            self._locked.pop(key, None)
            self._fails.pop(key, None)
        return None

    def record_failure(self, key: str, *, now: datetime) -> None:
        fails = [t for t in self._fails.get(key, []) if now - t < self.window]
        fails.append(now)
        self._fails[key] = fails
        if len(fails) >= self.max_attempts:
            self._locked[key] = now + self.lockout

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)
        self._locked.pop(key, None)

    def clear(self) -> None:
        self._fails.clear()
        self._locked.clear()


login_throttle = LoginThrottle(settings.login_max_attempts, settings.login_window_sec, settings.login_lockout_sec)
