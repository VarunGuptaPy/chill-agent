"""Pydantic settings — reads from .env file."""

from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    deepseek_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com"
    llm_temperature: float = 1.3

    # TTS
    tts_provider: str = "fish_audio"
    fish_audio_api_key: str = ""
    elevenlabs_api_key: str = ""
    tts_voice_id: str = ""

    # Images
    image_provider: str = "pollinations"
    image_width: int = 1920
    image_height: int = 1080
    # Pollinations (default — free, no key required)
    # Google Gemini (fallback)
    google_ai_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-preview-image-generation"
    image_rate_limit_seconds: float = 6.0  # Gemini free tier: ~10 RPM
    # Replicate / Flux (fallback)
    replicate_api_token: str = ""
    flux_model: str = "black-forest-labs/flux-schnell"
    nsfw_check_enabled: bool = True

    # YouTube
    youtube_client_secrets_file: Path = Path("./secrets/client_secret.json")
    youtube_token_file: Path = Path("./secrets/token.json")
    youtube_channel_id: str = ""

    # Scheduling
    videos_per_day: int = 4
    publish_hours_utc: str = "8,14,20,2"
    enable_captions: bool = True

    # Alerts
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    # Storage
    output_dir: Path = Path("./outputs")
    db_url: str = "sqlite:///./chill_agent.db"

    # Mode
    warmup_mode: bool = False

    @field_validator("publish_hours_utc")
    @classmethod
    def validate_hours(cls, v: str) -> str:
        hours = [int(h.strip()) for h in v.split(",")]
        for h in hours:
            if not 0 <= h <= 23:
                raise ValueError(f"Hour {h} out of range 0-23")
        return v

    @property
    def publish_hours_list(self) -> List[int]:
        return [int(h.strip()) for h in self.publish_hours_utc.split(",")]

    @property
    def effective_videos_per_day(self) -> int:
        if self.warmup_mode:
            return 1
        return self.videos_per_day


def get_settings() -> Settings:
    return Settings()
