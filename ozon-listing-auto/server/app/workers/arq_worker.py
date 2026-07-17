"""ARQ worker 入口配置：注册采集任务函数与 Redis 连接设置。"""
from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.collector import run_collect
from app.workers.matcher import run_match
from app.workers.scorer import run_score


class WorkerSettings:
    functions = [run_collect, run_match, run_score]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
