from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_")

    database_url: str = "sqlite:///./data/app.db"
    upload_dir: Path = Path("data/uploads")
    log_dir: Path = Path("logs")
    default_batch_size: int = 500


settings = Settings()
