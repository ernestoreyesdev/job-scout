from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-side configuration, read from the environment or services/agent/.env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    # Fernet key that encrypts users' API keys at rest.
    agent_encryption_key: str
    anthropic_api_key: str | None = None
    scoring_model: str = "claude-haiku-5-5"
    scoring_effort: str = "low"
    discovery_model: str = "claude-haiku-5-5"
    analysis_model: str = "claude-haiku-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
