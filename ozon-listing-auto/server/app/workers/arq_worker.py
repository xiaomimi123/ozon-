"""ARQ worker 入口配置：注册采集任务函数与 Redis 连接设置。"""
from arq import cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.workers.collector import run_collect
from app.workers.matcher import run_match
from app.workers.scorer import run_score
from app.workers.publisher import run_publish, run_publish_tick
from app.workers.imager import run_image_process


class WorkerSettings:
    functions = [run_collect, run_match, run_score, run_publish, run_publish_tick, run_image_process]
    cron_jobs = [cron(run_publish_tick, minute=set(range(0, 60)))]  # 每分钟扫一次到期草稿(§5.9)
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
