from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_KEY = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KALETA_", env_file=".env", extra="ignore")

    db_url: str = "sqlite+aiosqlite:///kaleta.db"
    host: str = "0.0.0.0"  # nosec B104 — intentional for Docker/container deployment
    port: int = 8080
    mode: str = "web"  # web | app | api
    secret_key: str = _INSECURE_KEY
    debug: bool = False

    @model_validator(mode="after")
    def _validate_secret_key(self) -> "Settings":
        if not self.debug and self.secret_key == _INSECURE_KEY:
            raise ValueError(
                "KALETA_SECRET_KEY must be set to a secure value in production. "
                "Set KALETA_DEBUG=true to bypass this check in development."
            )
        return self


settings = Settings()
