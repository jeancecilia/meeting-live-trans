from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Application
    app_env: str = "development"
    app_secret_key: str = "change-me"
    api_port: int = 8000

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "meeting_trans"
    postgres_user: str = "meeting_trans"
    postgres_password: str = "meeting_trans"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LiveKit
    livekit_host: str = "localhost"
    livekit_port: int = 7880
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    livekit_ws_url: str = "ws://localhost:7880"

    # OpenAI
    openai_api_key: str = "sk-change-me"
    openai_realtime_translate_model: str = "gpt-4o-mini-realtime"
    openai_realtime_transcribe_model: str = "gpt-4o-mini-realtime"
    openai_translation_model: str = "gpt-4o-mini"

    # JWT
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "http://localhost:3000"


settings = Settings()
