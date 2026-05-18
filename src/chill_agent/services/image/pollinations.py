"""Pollinations.ai image provider — free Flux API, no account required."""

from __future__ import annotations

import random
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import requests
import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

# Anonymous: Pollinations documents ~1 req/15s; use 16s to stay safe.
_ANON_DELAY_SECONDS = 16.0

# Retry waits per attempt on 429 or server error (seconds).
# 429 means rate-limited — wait much longer than normal backoff.
_RETRY_WAITS = [15, 30, 60]  # attempt 1→2, 2→3, 3→fail


class PollinationsImageProvider:
    BASE_URL = "https://image.pollinations.ai/prompt"

    # Negative prompt sent on every call to block unwanted art styles
    DEFAULT_NEGATIVE = (
        "sketchy lines, rough textures, cross-hatching, pencil marks, hand-drawn texture, "
        "shading on character, oval head, egg-shaped head, realistic proportions, "
        "muscular body, rounded limbs, detailed hands, fingers, boots, shoes, "
        "3D render, photorealistic, watercolor, oil painting"
    )

    def __init__(
        self,
        api_key: str = "",
        model: str = "flux",
        width: int = 1920,
        height: int = 1080,
        negative_prompt: str = "",
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model or "flux"
        self.default_width = width
        self.default_height = height
        self.negative_prompt = negative_prompt or self.DEFAULT_NEGATIVE
        self._last_call_at: float = 0.0

    def generate(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",  # accepted for protocol compat; width/height take precedence
        width: Optional[int] = None,
        height: Optional[int] = None,
        retries: int = 3,
    ) -> ImageResult:
        w = width if width is not None else self.default_width
        h = height if height is not None else self.default_height

        # Throttle anonymous calls to stay inside Pollinations' documented rate limit.
        if not self.api_key:
            elapsed = time.monotonic() - self._last_call_at
            remaining = _ANON_DELAY_SECONDS - elapsed
            if remaining > 0 and self._last_call_at > 0:
                logger.info("pollinations_rate_limit_wait", wait_seconds=round(remaining, 1))
                time.sleep(remaining)

        encoded = urllib.parse.quote(prompt)
        seed = random.randint(1, 999_999)

        url = f"{self.BASE_URL}/{encoded}"
        params: dict = {
            "width": w,
            "height": h,
            "model": self.model,
            "nologo": "true",
            "seed": seed,
            "negative": self.negative_prompt,
        }
        if self.api_key:
            params["key"] = self.api_key

        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            try:
                logger.info(
                    "pollinations_generate",
                    prompt=prompt[:80],
                    attempt=attempt + 1,
                    width=w,
                    height=h,
                    model=self.model,
                    has_key=bool(self.api_key),
                )
                resp = requests.get(url, params=params, timeout=120)
                self._last_call_at = time.monotonic()

                if resp.status_code == 200 and len(resp.content) > 1_000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(resp.content)
                    logger.info(
                        "pollinations_saved",
                        path=str(output_path),
                        size_bytes=len(resp.content),
                    )
                    return ImageResult(path=output_path, width=w, height=h, prompt_used=prompt)

                # Log the response body on non-200 so we can see what Pollinations says.
                body_preview = resp.text[:200] if resp.text else ""
                if resp.status_code == 429:
                    logger.warning(
                        "pollinations_rate_limited",
                        attempt=attempt + 1,
                        body=body_preview,
                        has_key=bool(self.api_key),
                    )
                else:
                    logger.warning(
                        "pollinations_bad_response",
                        status=resp.status_code,
                        size=len(resp.content),
                        body=body_preview,
                        attempt=attempt + 1,
                    )
                last_exc = RuntimeError(
                    f"HTTP {resp.status_code}: {body_preview[:120]}"
                )

            except Exception as exc:
                self._last_call_at = time.monotonic()
                logger.error("pollinations_request_error", error=str(exc), attempt=attempt + 1)
                last_exc = exc

            if attempt < retries - 1:
                wait = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                logger.info("pollinations_retry", wait_seconds=wait, attempt=attempt + 1)
                time.sleep(wait)

        raise RuntimeError(
            f"Pollinations: failed after {retries} attempts for prompt: {prompt[:80]}"
        ) from last_exc
