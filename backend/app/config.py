"""
Settings loaded from environment variables / .env.

Kept deliberately small: this demo only needs the OpenAI-compatible
client triple (API key, base URL, model name) plus two optional
per-role model overrides used to demonstrate multi-provider routing
and fallback, an optional demo passcode, and a database URL.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model_name: str = "gpt-4o-mini"

    # Optional overrides so the guardrail-evaluator step and the
    # fallback-regeneration step can literally target a different
    # provider/model (via an OpenAI-compatible multi-provider gateway
    # on OPENAI_BASE_URL) than the primary responder step.
    guardrail_model_name: Optional[str] = None
    fallback_model_name: Optional[str] = None

    demo_access_code: Optional[str] = None
    database_url: str = "sqlite:///./guardedcontext.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def guardrail_model(self) -> str:
        return self.guardrail_model_name or self.openai_model_name

    @property
    def fallback_model(self) -> str:
        return self.fallback_model_name or self.openai_model_name


@lru_cache
def get_settings() -> Settings:
    return Settings()
