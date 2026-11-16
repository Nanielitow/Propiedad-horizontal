from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    # Base de datos (rol app_user, sujeto a RLS)
    database_url: str
    sync_database_url: str
    migrations_database_url: str | None = None

    # Redis / Celery
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # S3
    s3_endpoint_url: str
    s3_public_endpoint_url: str
    s3_access_key_id: str
    s3_secret_access_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"
    s3_presigned_ttl_seconds: int = 300
    max_upload_mb: int = 50

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    # Auth
    jwt_secret: str
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 7
    cors_origins: str = "http://localhost:3000"  # separados por coma

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # IA
    llm_provider: Literal["openai", "gemini"] = "openai"
    # "fake": embeddings deterministas locales (desarrollo/tests sin API key)
    embedding_provider: Literal["openai", "gemini", "fake"] = "openai"
    openai_api_key: str = ""
    gemini_api_key: str = ""
    chat_model: str = "gpt-4.1-mini"
    extraction_model: str = "gpt-4.1-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    # Gemini 3: nivel de razonamiento interno del chat ("" = valor por defecto del modelo)
    chat_thinking_level: str = "minimal"
    # Buscador
    retrieval_top_k: int = 8
    chat_history_messages: int = 6

    # Correo (recordatorios). Sin SMTP_HOST no se envían correos (solo avisos en la app).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    smtp_from: str = "PH Gestión <no-responder@phgestion.local>"
    # URL pública del frontend, para los enlaces de los correos
    app_url: str = "http://localhost:3000"

    @model_validator(mode="after")
    def _production_safety(self) -> "Settings":
        """En producción, negarse a arrancar con secretos de ejemplo."""
        if self.environment == "production":
            if self.jwt_secret.startswith("change-me") or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET inseguro: use al menos 32 caracteres aleatorios en producción")
            if self.embedding_provider == "fake":
                raise ValueError("EMBEDDING_PROVIDER=fake no está permitido en producción")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
