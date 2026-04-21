"""Google Gemini image generation service."""

from __future__ import annotations

import os
import time
from pathlib import Path

import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

# Gemini free tier: ~10 RPM → 6 second gap between calls
_DEFAULT_RATE_LIMIT_SECONDS = 6.0


class GeminiImageClient:
    """Generate images using Google Gemini image generation API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        rate_limit_seconds: float = _DEFAULT_RATE_LIMIT_SECONDS,
    ) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_AI_API_KEY", "")
        self.model = model or os.environ.get(
            "GEMINI_IMAGE_MODEL",
            "gemini-2.5-flash-preview-image-generation",
        )
        self.rate_limit_seconds = rate_limit_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        retries: int = 3,
    ) -> ImageResult:
        from google.genai import types

        client = self._get_client()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["image", "text"],
                        image_config=types.ImageConfig(
                            aspect_ratio=aspect_ratio,
                        ),
                    ),
                )

                # Extract image from response parts
                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if (
                            part.inline_data
                            and part.inline_data.mime_type.startswith("image/")
                        ):
                            output_path.write_bytes(part.inline_data.data)

                            width, height = _aspect_ratio_to_dims(aspect_ratio)
                            logger.info(
                                "image_gemini_generated",
                                prompt=prompt[:80],
                                path=str(output_path),
                                aspect_ratio=aspect_ratio,
                                attempt=attempt + 1,
                            )

                            # Rate limit: sleep after successful generation
                            if self.rate_limit_seconds > 0:
                                time.sleep(self.rate_limit_seconds)

                            return ImageResult(
                                path=output_path,
                                width=width,
                                height=height,
                                prompt_used=prompt,
                            )

                # No image part in response
                response_text = ""
                try:
                    response_text = response.text or ""
                except Exception:
                    pass
                logger.warning(
                    "image_gemini_no_image_in_response",
                    prompt=prompt[:80],
                    attempt=attempt + 1,
                    response_text=response_text[:200],
                )
                last_exc = RuntimeError(f"No image returned by Gemini (attempt {attempt + 1})")

            except Exception as exc:
                last_exc = exc
                logger.error(
                    "image_gemini_failed",
                    prompt=prompt[:80],
                    attempt=attempt + 1,
                    error=str(exc)[:300],
                )

            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2 → 4 → 8 seconds
                logger.info("image_gemini_retry", wait_seconds=wait)
                time.sleep(wait)

        raise RuntimeError(
            f"Gemini image generation failed after {retries} attempts: {prompt[:80]}"
        ) from last_exc


def _aspect_ratio_to_dims(aspect_ratio: str) -> tuple[int, int]:
    """Return (width, height) for a given aspect ratio string."""
    mapping = {
        "16:9": (1280, 720),
        "9:16": (720, 1280),
        "4:3": (1024, 768),
        "3:4": (768, 1024),
        "1:1": (1024, 1024),
        "21:9": (1680, 720),
    }
    return mapping.get(aspect_ratio, (1280, 720))
