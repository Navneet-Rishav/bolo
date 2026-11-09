"""All configuration comes from environment variables, validated once at startup (pydantic-settings)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://postgres@localhost:5432/bolo"
    jwt_secret: str = Field(min_length=32)
    jwt_expires_minutes: int = 8 * 60
    cors_origins: str = "http://localhost:5173"

    # "demo" = offline rule-based understanding, no voice (tests, CI, public demo). "sarvam" = real STT/LLM/TTS.
    ai_provider: Literal["demo", "sarvam"] = "demo"
    sarvam_api_key: str | None = None
    sarvam_chat_model: str = "sarvam-105b"
    sarvam_tts_model: str = "bulbul:v4-flash"
    # Short structured extraction does not need long reasoning; set explicitly (see DECISIONS.md).
    sarvam_reasoning_effort: Literal["none", "low", "medium", "high"] | None = "low"

    timezone: str = "Asia/Kolkata"
    booking_window_days: int = 14
    min_lead_minutes: int = 30
    max_turns_per_call: int = 30
    calls_per_hour_per_ip: int = 20

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def check(self) -> "Settings":
        if self.ai_provider == "sarvam" and not self.sarvam_api_key:
            raise ValueError("AI_PROVIDER=sarvam requires SARVAM_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings().check()  # type: ignore[call-arg]
