from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://ozon:ozon@localhost:5432/ozon"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_minutes: int = 720
    # Fernet key（44 字符 base64）。生产从环境注入；默认仅供本地开发。
    fernet_key: str = "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
    cors_origins: list[str] = ["*"]
    # 货源匹配 embedder：mock（默认，无需 torch，docker compose up 一键跑通用）或
    # clip（真实 ChineseClipEmbedder，需 worker 镜像以 INSTALL_ML=true 构建）。
    embedder: str = "mock"
    # LLM 服务：mock（默认，无需 key）或 openai（OpenAI 兼容接口，默认通义千问 DashScope）。
    llm_provider: str = "mock"          # mock | openai
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-plus"
    # Ozon 跟卖挂靠：mock（默认，无需真实凭据）或 real（真实调用 Ozon Seller API，需店铺真实凭据）。
    ozon_seller_provider: str = "mock"   # mock | real; 真实挂靠需配 real + 店铺真实凭据
    # 进度广播后端：memory（默认，单进程本地 fan-out）或 redis（跨进程 pub/sub，worker/API 分离时用）。
    progress_backend: str = "memory"    # memory | redis
    # 改图 provider：mock(默认) | local(Pillow 真实) | openai_compat | http。本地类操作恒走 local。
    image_provider: str = "mock"
    # 登录失败限流（§3.2）：窗口内失败达 max 次锁定 lockout 秒。
    login_max_attempts: int = 5
    login_window_sec: int = 300
    login_lockout_sec: int = 900

settings = Settings()
