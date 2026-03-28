"""
OmniDrop AI — Application Configuration
All settings are read from environment variables via Pydantic BaseSettings.
Never hardcode secrets here.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_env: Literal["local", "dev", "sandbox", "production"] = Field(
        default="local", validation_alias="APP_ENV"
    )
    app_secret_key: str = Field(..., validation_alias="APP_SECRET_KEY")

    # Supabase
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    # SUPABASE_KEY is the anon key (safe for client-side use)
    supabase_key: str = Field(..., validation_alias="SUPABASE_KEY")
    supabase_service_role_key: str = Field(..., validation_alias="SUPABASE_SERVICE_ROLE_KEY")

    # Anthropic (default model: claude-opus-4-6)
    anthropic_api_key: str = Field(..., validation_alias="ANTHROPIC_API_KEY")

    # AccuLynx
    acculynx_api_key: str = Field(..., validation_alias="ACCULYNX_API_KEY")
    # Used by Hookdeck to validate events from AccuLynx before forwarding
    hookdeck_signing_secret: str = Field(..., validation_alias="HOOKDECK_SIGNING_SECRET")

    # Celery + Redis (replaces Temporal)
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0", validation_alias="CELERY_BROKER_URL"
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0", validation_alias="CELERY_RESULT_BACKEND"
    )

    # WorkOS (Auth & SSO)
    workos_api_key: str = Field(..., validation_alias="WORKOS_API_KEY")
    workos_client_id: str = Field(..., validation_alias="WORKOS_CLIENT_ID")
    workos_cookie_password: str = Field(..., validation_alias="WORKOS_COOKIE_PASSWORD")

    # Unstructured.io (Omni-Parser)
    unstructured_api_key: str = Field(..., validation_alias="UNSTRUCTURED_API_KEY")

    # Sentry — optional, disabled if DSN is not set
    sentry_python_dsn: str | None = Field(default=None, validation_alias="SENTRY_PYTHON_DSN")
    sentry_traces_sample_rate: float = Field(
        default=1.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    @property
    def cors_origins(self) -> list[str]:
        origins = {
            "local": ["http://localhost:3000"],
            "dev": ["https://omnidrop.dev"],
            "sandbox": ["https://sandbox.omnidrop.dev"],
            "production": ["https://omnidrop.ai"],
        }
        return origins.get(self.app_env, ["http://localhost:3000"])

    model_config = {"env_file": ".env", "case_sensitive": False}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
