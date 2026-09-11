from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env robustly regardless of CWD:
# backend/core/config.py -> backend/ -> project root/.env, fallback backend/.env
_CORE_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _CORE_DIR.parent
_PROJECT_ROOT = _BACKEND_DIR.parent
_ENV_CANDIDATES = [_PROJECT_ROOT / ".env", _BACKEND_DIR / ".env"]
_ENV_FILE = next((str(p) for p in _ENV_CANDIDATES if p.exists()), str(_ENV_CANDIDATES[0]))


class Settings(BaseSettings):
    YOUTUBE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DATABASE_URL: str = (
        "postgresql+asyncpg://echolens:echolens_password@localhost:5432/echolens_db"
    )
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Hardening / operational ---
    # If set, destructive endpoints (reset-database) require header X-Admin-Token.
    ADMIN_TOKEN: str = ""
    # Comma-separated CORS origins.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Global caps (server-side). Frontend settings UI must stay within these.
    MAX_PROCESS_LIMIT: int = 2000
    MAX_COMMENT_PAGE_SIZE: int = 100
    MAX_CHAT_CONTEXT: int = 100
    MAX_QUESTION_LENGTH: int = 1000
    # Default chat context: fraction of comments sent to the LLM + bounds.
    CHAT_CONTEXT_FRACTION: float = 0.25
    CHAT_CONTEXT_MIN: int = 20

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if v and v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v and v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v = (v or "INFO").upper()
        return v if v in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else "INFO"

    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
