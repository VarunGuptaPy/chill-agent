"""Replicate Flux 1.1 Pro image generation adapter."""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Tuple

import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

# Flux 1.1 Pro hard limits
_FLUX_MAX_WIDTH = 1440
_FLUX_MAX_HEIGHT = 1440


class ReplicateFluxClient:
    def __init__(self, api_token: str, model: str = "black-forest-labs/flux-1.1-pro") -> None:
        self._api_token = api_token
        self._model = model

    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: Tuple[int, int] = (1920, 1080),
    ) -> ImageResult:
        import replicate

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Clamp to Flux 1.1 Pro's hard limits while preserving aspect ratio
        width, height = _clamp_size(size[0], size[1])

        logger.info(
            "image_replicate_request",
            model=self._model,
            width=width,
            height=height,
            prompt_chars=len(prompt),
        )

        client = replicate.Client(api_token=self._api_token)

        # Retry loop with 429-aware backoff
        last_exc = None
        for attempt, wait in enumerate([0, 15, 30, 60], start=1):
            if wait:
                logger.warning(
                    "image_replicate_retry",
                    attempt=attempt,
                    wait_seconds=wait,
                )
                time.sleep(wait)
            try:
                output = client.run(
                    self._model,
                    input={
                        "prompt": prompt,
                        "width": width,
                        "height": height,
                        "output_format": "png",
                        "output_quality": 95,
                        "safety_tolerance": 2,
                        "prompt_upsampling": True,
                    },
                )
                break
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status", None)
                if status == 429:
                    logger.warning(
                        "image_replicate_rate_limited",
                        attempt=attempt,
                        error=str(exc)[:200],
                    )
                    if attempt >= 4:
                        logger.error("image_replicate_gave_up", attempts=4)
                        raise
                    continue
                # Non-429 error: raise immediately (don't waste retries)
                logger.error("image_replicate_error", status=status, error=str(exc)[:200])
                raise
        else:
            raise last_exc

        # Replicate returns a URL or file-like object
        if isinstance(output, list):
            url = str(output[0])
        else:
            url = str(output)

        urllib.request.urlretrieve(url, str(output_path))

        logger.info(
            "image_replicate_done",
            output=str(output_path),
            width=width,
            height=height,
        )

        return ImageResult(
            path=output_path,
            width=width,
            height=height,
            prompt_used=prompt,
        )


def _clamp_size(width: int, height: int) -> Tuple[int, int]:
    """Scale down to fit within Flux's max dimensions, preserving aspect ratio."""
    if width <= _FLUX_MAX_WIDTH and height <= _FLUX_MAX_HEIGHT:
        return width, height
    ratio = min(_FLUX_MAX_WIDTH / width, _FLUX_MAX_HEIGHT / height)
    # Round to nearest multiple of 8 (Flux requirement)
    new_w = int(width * ratio) // 8 * 8
    new_h = int(height * ratio) // 8 * 8
    return max(new_w, 8), max(new_h, 8)
