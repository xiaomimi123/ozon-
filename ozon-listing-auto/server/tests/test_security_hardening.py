import pytest
from datetime import datetime, timezone, timedelta
from starlette.middleware.cors import CORSMiddleware
from app.core.login_throttle import LoginThrottle, login_throttle
from app.core.security import hash_password
from app.models import User

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)


def test_throttle_locks_after_max_attempts():
    t = LoginThrottle(max_attempts=3, window_sec=300, lockout_sec=900)
    for i in range(3):
        assert t.check("k", now=_NOW) is None
        t.record_failure("k", now=_NOW)
    rem = t.check("k", now=_NOW)
    assert rem is not None and rem > 0                     # 锁定, 返回剩余秒
    assert t.check("k", now=_NOW + timedelta(seconds=901)) is None   # 锁定过期→放行


def test_throttle_window_expiry_drops_old_failures():
    t = LoginThrottle(max_attempts=3, window_sec=300, lockout_sec=900)
    t.record_failure("k", now=_NOW)
    t.record_failure("k", now=_NOW + timedelta(seconds=400))   # 超窗, 旧的应失效
    t.record_failure("k", now=_NOW + timedelta(seconds=401))
    assert t.check("k", now=_NOW + timedelta(seconds=402)) is None  # 窗口内仅2次<3, 未锁


def test_throttle_reset_clears():
    t = LoginThrottle(max_attempts=2, window_sec=300, lockout_sec=900)
    t.record_failure("k", now=_NOW); t.record_failure("k", now=_NOW)
    assert t.check("k", now=_NOW) is not None
    t.reset("k")
    assert t.check("k", now=_NOW) is None


def test_cors_middleware_reads_settings():
    from app.main import app
    from app.core.config import settings
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS 中间件未注册"
    assert cors[0].kwargs.get("allow_origins") == settings.cors_origins   # 配置驱动, 非硬编码字面量
    assert cors[0].kwargs.get("allow_credentials") in (False, None)


@pytest.mark.asyncio
async def test_login_rate_limited_after_failures(client, db_session):
    login_throttle.clear()                                  # 单例跨测试隔离
    db_session.add(User(username="thr", password_hash=hash_password("right"), role="operator"))
    await db_session.commit()
    for _ in range(5):
        r = await client.post("/auth/login", data={"username": "thr", "password": "wrong"})
        assert r.status_code == 401
    r = await client.post("/auth/login", data={"username": "thr", "password": "wrong"})
    assert r.status_code == 429 and "Retry-After" in r.headers
    login_throttle.clear()
    ok = await client.post("/auth/login", data={"username": "thr", "password": "right"})
    assert ok.status_code == 200 and ok.json()["access_token"]


@pytest.mark.asyncio
async def test_login_throttle_keys_on_real_ip_not_spoofable_xff(client, db_session):
    # 回归测试：nginx 用 $proxy_add_x_forwarded_for 会在 XFF 上"追加"真实连入 IP，
    # 客户端可在自己发的请求里预先塞一个假的第一段、每次换一个，从而在旧的
    # "取 XFF 首段" 逻辑下让限流 key 每次都不同、绕过锁定。
    # X-Real-IP 由 nginx 用 $remote_addr 覆盖写入，客户端发送的值到不了后端，权威可信。
    login_throttle.clear()
    db_session.add(User(username="thr2", password_hash=hash_password("right"), role="operator"))
    await db_session.commit()
    for i in range(5):
        r = await client.post(
            "/auth/login",
            data={"username": "thr2", "password": "wrong"},
            headers={
                "X-Real-IP": "9.9.9.9",
                "X-Forwarded-For": f"1.2.3.{i}, 9.9.9.9",   # 每次伪造不同的首段
            },
        )
        assert r.status_code == 401
    r = await client.post(
        "/auth/login",
        data={"username": "thr2", "password": "wrong"},
        headers={
            "X-Real-IP": "9.9.9.9",
            "X-Forwarded-For": "6.6.6.6, 9.9.9.9",   # 首段又换了一个, 但 X-Real-IP 不变
        },
    )
    assert r.status_code == 429 and "Retry-After" in r.headers
    login_throttle.clear()
