from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    secret_key: str = Field(min_length=32)
    # True, чтобы cookie не ушла по HTTP. Локальный .env явно ставит false.
    cookie_secure: bool = True
    session_ttl_days: int = 30
    # IP или CIDR доверенного прокси через запятую. Пусто — не читать X-Forwarded-For.
    trusted_proxies: str = ""

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_random(cls, value: str) -> str:
        if "change-me" in value.lower():
            raise ValueError(
                "SECRET_KEY — заготовка из примера. Сгенерируйте случайную строку: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value


settings = Settings()
