"""Replicate Flux image generation adapter.

Default model: flux-schnell — faster, cheaper ($0.003/image), and steerable
toward simple/crude art styles without over-polishing the output.
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Tuple

import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

# Flux model dimension limits
_FLUX_MAX_DIM = 1440


class ReplicateFluxClient:
    def __init__(
        self,
        api_token: str,
        model: str = "black-forest-labs/flux-schnell",
    ) -> None:
        self._api_token = api_token
        self._model = model

    def generate(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
    ) -> ImageResult:
        import replicate

        output_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = _clamp_size(width, height)

        logger.info(
            "image_replicate_request",
            model=self._model,
            width=width,
            height=height,
            prompt_chars=len(prompt),
        )

        client = replicate.Client(api_token=self._api_token)

        # Model-specific input params
        is_schnell = "schnell" in self._model
        model_input = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "output_format": "png",
            "output_quality": 95,
            "disable_safety_checker": False,  # Keep safety ON always
        }
        if not is_schnell:
            # flux-1.1-pro extra params
            model_input["safety_tolerance"] = 2
            model_input["prompt_upsampling"] = True

        # Retry loop with 429-aware backoff
        last_exc = None
        for attempt, wait in enumerate([0, 15, 30, 60], start=1):
            if wait:
                logger.warning("image_replicate_retry", attempt=attempt, wait_seconds=wait)
                time.sleep(wait)
            try:
                output = client.run(self._model, input=model_input)
                break
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status", None)
                if status == 402:
                    # Billing error — never retryable
                    logger.error(
                        "image_replicate_insufficient_credit",
                        message="Add credits at https://replicate.com/account/billing",
                    )
                    raise
                if status == 429:
                    logger.warning(
                        "image_replicate_rate_limited",
                        attempt=attempt,
                        error=str(exc)[:200],
                    )
                    if attempt >= 4:
                        logger.error("image_replicate_gave_up")
                        raise
                    continue
                logger.error("image_replicate_error", status=status, error=str(exc)[:200])
                raise
        else:
            raise last_exc  # type: ignore[misc]

        # Replicate returns URL or file-like object
        if isinstance(output, list):
            url = str(output[0])
        else:
            url = str(output)

        urllib.request.urlretrieve(url, str(output_path))

        logger.info("image_replicate_done", output=str(output_path), width=width, height=height)

        return ImageResult(
            path=output_path,
            width=width,
            height=height,
            prompt_used=prompt,
        )


def _clamp_size(width: int, height: int) -> Tuple[int, int]:
    """Scale down to fit within Flux's max dimensions, preserving aspect ratio."""
    if width <= _FLUX_MAX_DIM and height <= _FLUX_MAX_DIM:
        return width, height
    ratio = min(_FLUX_MAX_DIM / width, _FLUX_MAX_DIM / height)
    new_w = int(width * ratio) // 8 * 8
    new_h = int(height * ratio) // 8 * 8
    return max(new_w, 8), max(new_h, 8)
