"""Pollinations.ai image generation provider.

Free, no API key required. Uses the Flux model via a simple HTTP GET.
https://image.pollinations.ai/prompt/{encoded_prompt}
"""

from __future__ import annotations

import random
import time
import urllib.parse
from pathlib import Path

import requests
import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

_BASE_URL = "https://image.pollinations.ai/prompt"
_RATE_LIMIT_SECONDS = 3.0  # be respectful of the free service
_MIN_RESPONSE_BYTES = 1000  # guard against empty/error responses


class PollinationsImageClient:
    """Generate images via Pollinations.ai — free, no API key needed."""

    def __init__(self, rate_limit_seconds: float = _RATE_LIMIT_SECONDS) -> None:
        self.rate_limit_seconds = rate_limit_seconds

    def generate(
        self,
        prompt: str,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
        retries: int = 3,
    ) -> ImageResult:
        encoded = urllib.parse.quote(prompt, safe="")
        seed = random.randint(1, 999_999)
        url = (
            f"{_BASE_URL}/{encoded}"
            f"?width={width}&height={height}&model=flux&nologo=true&seed={seed}"
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None

        for attempt in range(retries):
            try:
                resp = requests.get(url, timeout=120)
                if resp.status_code == 200 and len(resp.content) >= _MIN_RESPONSE_BYTES:
                    output_path.write_bytes(resp.content)
                    logger.info(
                        "image_pollinations_generated",
                        prompt=prompt[:80],
                        path=str(output_path),
                        width=width,
                        height=height,
                        attempt=attempt + 1,
                        bytes=len(resp.content),
                    )
                    if self.rate_limit_seconds > 0:
                        time.sleep(self.rate_limit_seconds)
                    return ImageResult(
                        path=output_path,
                        width=width,
                        height=height,
                        prompt_used=prompt,
                    )

                # Non-200 or suspiciously small response
                last_exc = RuntimeError(
                    f"Pollinations returned status={resp.status_code} "
                    f"bytes={len(resp.content)} (attempt {attempt + 1})"
                )
                logger.warning(
                    "image_pollinations_bad_response",
                    status=resp.status_code,
                    bytes=len(resp.content),
                    attempt=attempt + 1,
                )

            except Exception as exc:
                last_exc = exc
                logger.error(
                    "image_pollinations_failed",
                    prompt=prompt[:80],
                    attempt=attempt + 1,
                    error=str(exc)[:300],
                )

            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)  # 2 → 4 → 8 seconds
                logger.info("image_pollinations_retry", wait_seconds=wait)
                time.sleep(wait)

        raise RuntimeError(
            f"Pollinations image generation failed after {retries} attempts: {prompt[:80]}"
        ) from last_exc
