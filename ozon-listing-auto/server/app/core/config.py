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

settings = Settings()
