from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    app_env: str = "development"
    app_secret_key: str = "change-me"
    api_port: int = 8000

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "meeting_trans"
    postgres_user: str = "meeting_trans"
    postgres_password: str = "meeting_trans"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def database_url_sync(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    redis_url: str = "redis://localhost:6379/0"

    livekit_host: str = "localhost"
    livekit_port: int = 7880
    livekit_api_key: str = "devkey"
    livekit_api_secret: str = "secret"
    livekit_ws_url: str = "ws://localhost:7880"          # internal / worker use
    livekit_public_ws_url: str = "ws://localhost:7880"    # returned to browsers

    openai_api_key: str = "sk-change-me"
    openai_realtime_translate_model: str = "gpt-realtime-translate"
    openai_realtime_transcribe_model: str = "gpt-realtime-whisper"
    openai_translation_model: str = "gpt-4o-mini"

    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    caption_worker_service_token: str = "change-me-worker-service-token"

    cors_origins: str = "http://localhost:3000"


settings = Settings()
