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

settings = Settings()
