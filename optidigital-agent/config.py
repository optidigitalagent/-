from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: int
    OPENAI_API_KEY: str
    FREELANCEHUNT_TOKEN: str
    DATABASE_URL: str


settings = Settings()
