from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: int
    ADMIN_CHAT_ID: Optional[int] = None
    OPENAI_API_KEY: Optional[str] = None
    FREELANCEHUNT_TOKEN: Optional[str] = None
    DATABASE_URL: str

    # Gmail agent settings (all optional — disabled by default)
    GMAIL_ENABLED: bool = False
    GMAIL_USE_MOCK: bool = True
    GMAIL_CREDENTIALS_FILE: str = "credentials.json"
    GMAIL_TOKEN_FILE: str = "gmail_token.json"
    GMAIL_CREDENTIALS_JSON: Optional[str] = None  # Railway-safe: JSON content
    GMAIL_TOKEN_JSON: Optional[str] = None        # Railway-safe: JSON content
    GMAIL_MIN_SCORE: float = 6.0
    GMAIL_CHECK_INTERVAL_MINUTES: int = 60
    GMAIL_DIGEST_ENABLED: bool = False

    @property
    def admin_chat_id(self) -> int:
        return self.ADMIN_CHAT_ID if self.ADMIN_CHAT_ID is not None else self.TELEGRAM_CHAT_ID


settings = Settings()
