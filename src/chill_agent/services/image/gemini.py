"""Google Vertex AI image generation service (Imagen 3 via google-genai SDK)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

_DEFAULT_LOCATION = "us-central1"


class GeminiImageClient:
    """Generate images using Vertex AI (Imagen 3 or Gemini image models)."""

    def __init__(
        self,
        key_file: str | None = None,
        project: str | None = None,
        location: str | None = None,
        model: str | None = None,
        rate_limit_seconds: float = 0.0,
    ) -> None:
        self.key_file = key_file or os.environ.get("VERTEX_AI_KEY_FILE", "")
        self.project = project or os.environ.get("VERTEX_AI_PROJECT", "dubmanandyoutube")
        self.location = location or os.environ.get("VERTEX_AI_LOCATION", _DEFAULT_LOCATION)
        self.model = model or os.environ.get(
            "GEMINI_IMAGE_MODEL", "imagen-3.0-generate-001"
        )
        self.rate_limit_seconds = rate_limit_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                self.key_file,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self._client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                credentials=credentials,
            )
        return self._client

    def generate(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
        retries: int = 3,
        width=None,
        height=None,
    ) -> ImageResult:
        client = self._get_client()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                if "imagen" in self.model.lower():
                    result = self._generate_imagen(client, prompt, output_path, aspect_ratio)
                else:
                    result = self._generate_gemini(client, prompt, output_path, aspect_ratio)

                logger.info(
                    "image_vertex_generated",
                    model=self.model,
                    prompt=prompt[:80],
                    path=str(output_path),
                    attempt=attempt + 1,
                )
                if self.rate_limit_seconds > 0:
                    time.sleep(self.rate_limit_seconds)
                return result

            except Exception as exc:
                last_exc = exc
                logger.error(
                    "image_vertex_failed",
                    prompt=prompt[:80],
                    attempt=attempt + 1,
                    error=str(exc)[:300],
                )
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                logger.info("image_vertex_retry", wait_seconds=wait)
                time.sleep(wait)

        raise RuntimeError(
            f"Vertex AI image generation failed after {retries} attempts: {prompt[:80]}"
        ) from last_exc

    def _generate_imagen(
        self, client, prompt: str, output_path: Path, aspect_ratio: str
    ) -> ImageResult:
        from google.genai import types

        response = client.models.generate_images(
            model=self.model,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio=aspect_ratio,
            ),
        )
        if not response.generated_images:
            raise RuntimeError("Imagen returned no images")

        image_bytes = response.generated_images[0].image.image_bytes
        output_path.write_bytes(image_bytes)
        w, h = _aspect_ratio_to_dims(aspect_ratio)
        return ImageResult(path=output_path, width=w, height=h, prompt_used=prompt)

    def _generate_gemini(
        self, client, prompt: str, output_path: Path, aspect_ratio: str
    ) -> ImageResult:
        from google.genai import types

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["image", "text"],
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            ),
        )
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    output_path.write_bytes(part.inline_data.data)
                    w, h = _aspect_ratio_to_dims(aspect_ratio)
                    return ImageResult(path=output_path, width=w, height=h, prompt_used=prompt)
        raise RuntimeError("Gemini returned no image part in response")


def _aspect_ratio_to_dims(aspect_ratio: str) -> tuple[int, int]:
    mapping = {
        "16:9": (1024, 576),
        "9:16": (576, 1024),
        "4:3": (768, 576),
        "3:4": (576, 768),
        "1:1": (1024, 1024),
        "21:9": (1024, 439),
    }
    return mapping.get(aspect_ratio, (1024, 576))
