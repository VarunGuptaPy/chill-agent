"""SDXL local fallback image generation adapter.

Requires: diffusers, torch, transformers
Used when REPLICATE_API_TOKEN is not set or for offline/zero-cost testing.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Dict, Tuple

import structlog

from chill_agent.services.image.base import ImageResult
from chill_agent.utils.retry import with_retry

logger = structlog.get_logger()


class SDXLLocalClient:
    """Local SDXL pipeline via diffusers. Lazy-loads on first call."""

    def __init__(self) -> None:
        self._pipe = None

    def _load_pipeline(self):
        if self._pipe is not None:
            return self._pipe

        try:
            import torch
            from diffusers import DiffusionPipeline

            logger.info("sdxl_loading_pipeline")
            pipe = DiffusionPipeline.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                use_safetensors=True,
                variant="fp16" if torch.cuda.is_available() else None,
            )
            if torch.cuda.is_available():
                pipe = pipe.to("cuda")
            self._pipe = pipe
            return self._pipe
        except ImportError as e:
            raise RuntimeError(
                "SDXL local requires: pip install diffusers transformers torch accelerate"
            ) from e

    @with_retry(attempts=2, backoff=(5.0, 15.0))
    def generate(
        self,
        prompt: str,
        output_path: Path,
        aspect_ratio: str = "16:9",
    ) -> ImageResult:
        _AR: Dict[str, Tuple[int, int]] = {
            "16:9": (1280, 720), "9:16": (720, 1280),
            "4:3": (1024, 768), "1:1": (1024, 1024),
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = _AR.get(aspect_ratio, (1280, 720))

        pipe = self._load_pipeline()
        logger.info("sdxl_generating", width=width, height=height)

        result = pipe(
            prompt=prompt,
            width=min(width, 1280),   # SDXL caps at 1280 in most configs
            height=min(height, 768),
            num_inference_steps=30,
            guidance_scale=7.5,
        )
        image = result.images[0]

        # Resize to target if needed
        if image.size != (width, height):
            from PIL import Image as PilImage

            image = image.resize((width, height), PilImage.LANCZOS)

        image.save(str(output_path), "PNG")

        logger.info("sdxl_done", output=str(output_path))

        return ImageResult(
            path=output_path,
            width=width,
            height=height,
            prompt_used=prompt,
        )
