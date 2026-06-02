from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: int
    ADMIN_CHAT_ID: Optional[int] = None
    OPENAI_API_KEY: str
    FREELANCEHUNT_TOKEN: str
    DATABASE_URL: str

    @property
    def admin_chat_id(self) -> int:
        return self.ADMIN_CHAT_ID if self.ADMIN_CHAT_ID is not None else self.TELEGRAM_CHAT_ID


settings = Settings()
