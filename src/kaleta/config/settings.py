from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KALETA_", env_file=".env", extra="ignore")

    db_url: str = "sqlite+aiosqlite:///kaleta.db"
    host: str = "0.0.0.0"
    port: int = 8080
    mode: str = "web"  # web | app | api
    secret_key: str = "change-me-in-production"
    debug: bool = False


settings = Settings()
