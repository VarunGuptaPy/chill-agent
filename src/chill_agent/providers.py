"""Factory functions to build configured service providers from Settings."""

from __future__ import annotations

from typing import Optional

import structlog

from chill_agent.config import Settings

logger = structlog.get_logger()


def build_llm(settings: Settings):
    from chill_agent.services.llm.deepseek import DeepSeekClient

    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY is not set. Add it to your .env file.")

    return DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
    )


def build_tts(settings: Settings):
    provider = settings.tts_provider.lower()

    if provider == "fish_audio":
        from chill_agent.services.tts.fish_audio import FishAudioTTS

        if not settings.fish_audio_api_key:
            raise ValueError("FISH_AUDIO_API_KEY is not set. Add it to your .env file.")
        return FishAudioTTS(api_key=settings.fish_audio_api_key)

    elif provider == "elevenlabs":
        from chill_agent.services.tts.elevenlabs import ElevenLabsTTS

        if not settings.elevenlabs_api_key:
            raise ValueError("ELEVENLABS_API_KEY is not set. Add it to your .env file.")
        return ElevenLabsTTS(api_key=settings.elevenlabs_api_key)

    else:
        raise ValueError(f"Unknown TTS provider: {provider}. Use 'fish_audio' or 'elevenlabs'.")


def build_image_provider(settings: Settings):
    provider = settings.image_provider.lower()

    if provider == "pollinations":
        from chill_agent.services.image.pollinations import PollinationsImageClient

        return PollinationsImageClient()

    elif provider == "gemini":
        from chill_agent.services.image.gemini import GeminiImageClient

        if not settings.google_ai_api_key:
            raise ValueError(
                "GOOGLE_AI_API_KEY is not set. Get one free at https://aistudio.google.com/apikey"
            )
        return GeminiImageClient(
            api_key=settings.google_ai_api_key,
            model=settings.gemini_image_model,
            rate_limit_seconds=settings.image_rate_limit_seconds,
        )

    elif provider == "replicate_flux":
        from chill_agent.services.image.replicate_flux import ReplicateFluxClient

        if not settings.replicate_api_token:
            raise ValueError("REPLICATE_API_TOKEN is not set. Add it to your .env file.")
        return ReplicateFluxClient(
            api_token=settings.replicate_api_token,
            model=settings.flux_model,
        )

    elif provider == "sdxl_local":
        from chill_agent.services.image.sdxl_local import SDXLLocalClient

        logger.warning(
            "sdxl_local_selected",
            message="Using local SDXL. Image quality will be lower than Flux.",
        )
        return SDXLLocalClient()

    elif provider == "local_placeholder":
        from chill_agent.services.image.local_placeholder import LocalPlaceholderClient

        logger.warning(
            "local_placeholder_selected",
            message="Using local placeholder images. For testing only — not for real videos.",
        )
        return LocalPlaceholderClient()

    else:
        raise ValueError(
            f"Unknown image provider: {provider}. "
            "Use 'pollinations', 'gemini', 'replicate_flux', 'sdxl_local', or 'local_placeholder'."
        )


def build_youtube(settings: Settings) -> Optional[object]:
    from chill_agent.services.youtube.client import YouTubeClient

    if not settings.youtube_client_secrets_file.exists():
        logger.warning(
            "youtube_not_configured",
            message="YouTube client secrets not found. Upload will be skipped.",
            path=str(settings.youtube_client_secrets_file),
        )
        return None

    return YouTubeClient(
        client_secrets_file=settings.youtube_client_secrets_file,
        token_file=settings.youtube_token_file,
    )
