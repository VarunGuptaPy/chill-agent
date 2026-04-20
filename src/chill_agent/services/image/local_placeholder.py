"""Local placeholder image provider — generates colored PNG stubs using PIL.

Use this for dry-runs and testing when you don't want to spend Replicate credits.
Set IMAGE_PROVIDER=local_placeholder in .env or pass --mock-images to dry-run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

import structlog

from chill_agent.services.image.base import ImageResult

logger = structlog.get_logger()

# A small palette of muted pastel colors to cycle through
_COLORS = [
    (173, 216, 230),  # light blue
    (144, 238, 144),  # light green
    (255, 228, 181),  # moccasin
    (221, 160, 221),  # plum
    (240, 230, 140),  # khaki
    (175, 238, 238),  # pale turquoise
    (255, 182, 193),  # light pink
    (210, 180, 140),  # tan
]


class LocalPlaceholderClient:
    """Generates simple colored PNG images locally — zero API calls, zero cost."""

    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: Tuple[int, int] = (1920, 1080),
    ) -> ImageResult:
        from PIL import Image, ImageDraw, ImageFont

        output_path.parent.mkdir(parents=True, exist_ok=True)
        width, height = size

        # Pick a deterministic color based on prompt hash
        color_idx = int(hashlib.md5(prompt.encode()).hexdigest(), 16) % len(_COLORS)
        bg_color = _COLORS[color_idx]

        img = Image.new("RGB", (width, height), color=bg_color)
        draw = ImageDraw.Draw(img)

        # Draw a simple stick figure in the center
        _draw_stick_figure(draw, width // 2, height // 2, scale=min(width, height) // 6)

        # Write a snippet of the prompt as a label
        label = prompt[:80] + ("..." if len(prompt) > 80 else "")
        try:
            from PIL import ImageFont
            font = ImageFont.load_default()
        except Exception:
            font = None

        draw.text((20, 20), "[PLACEHOLDER]", fill=(60, 60, 60), font=font)
        draw.text((20, 50), label, fill=(80, 80, 80), font=font)

        img.save(str(output_path), "PNG")

        logger.debug(
            "image_placeholder_generated",
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


def _draw_stick_figure(draw, cx: int, cy: int, scale: int) -> None:
    """Draw a simple stick figure centered at (cx, cy)."""
    r = scale // 4  # head radius
    # Head
    draw.ellipse([cx - r, cy - scale - r, cx + r, cy - scale + r], outline=(40, 40, 40), width=3)
    # Body
    draw.line([cx, cy - scale + r, cx, cy], fill=(40, 40, 40), width=3)
    # Arms
    draw.line([cx - scale // 3, cy - scale // 2, cx + scale // 3, cy - scale // 2], fill=(40, 40, 40), width=3)
    # Legs
    draw.line([cx, cy, cx - scale // 3, cy + scale // 2], fill=(40, 40, 40), width=3)
    draw.line([cx, cy, cx + scale // 3, cy + scale // 2], fill=(40, 40, 40), width=3)
