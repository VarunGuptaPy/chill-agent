"""Stage 7: Thumbnail — overlays bold title text on the generated image."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import structlog

logger = structlog.get_logger()

_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"


def make_thumbnail(
    raw_image_path: Path,
    title: str,
    output_root: Path,
    run_id: str,
    force: bool = False,
) -> Tuple[Path, Path]:
    """Generate two thumbnail variants (A/B) with text overlay.

    Returns (thumbnail_a_path, thumbnail_b_path).
    """
    from chill_agent.utils.paths import thumbnail_a_path, thumbnail_b_path

    path_a = thumbnail_a_path(output_root, run_id)
    path_b = thumbnail_b_path(output_root, run_id)

    if path_a.exists() and path_b.exists() and not force:
        logger.info("thumbnail_cache_hit")
        return path_a, path_b

    # Get 3-5 bold words from title for overlay
    words = title.split()
    overlay_text = " ".join(words[:5]).upper()

    _render_thumbnail(raw_image_path, overlay_text, path_a, text_position="bottom_left")
    _render_thumbnail(raw_image_path, overlay_text, path_b, text_position="top_right")

    logger.info("thumbnails_created", a=str(path_a), b=str(path_b))
    return path_a, path_b


def _render_thumbnail(
    source: Path,
    text: str,
    output: Path,
    text_position: str = "bottom_left",
    target_size: Tuple[int, int] = (1280, 720),
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(str(source)).convert("RGB")
    img = img.resize(target_size, Image.LANCZOS)

    draw = ImageDraw.Draw(img)

    # Load font
    font_size = 90
    font = _load_font(font_size)

    # Wrap text to fit
    lines = _wrap_text(text, font, draw, max_width=int(target_size[0] * 0.75))

    line_height = font_size + 10
    total_text_height = len(lines) * line_height

    w, h = target_size

    if text_position == "bottom_left":
        x = 40
        y = h - total_text_height - 60
    elif text_position == "top_right":
        # Right-align
        max_line_w = max(draw.textlength(l, font=font) for l in lines) if lines else 200
        x = w - int(max_line_w) - 40
        y = 60
    else:
        x, y = 40, 60

    # Draw each line with thick black stroke + white fill
    for line in lines:
        _draw_text_with_stroke(draw, line, x, y, font, fill="white", stroke="black", stroke_width=4)
        y += line_height

    # Slight red accent bar under text (optional)
    bar_y = y + 5
    draw.rectangle([x - 5, bar_y, x + 300, bar_y + 6], fill="#E53935")

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output), "JPEG", quality=95)


def _load_font(size: int):
    from PIL import ImageFont

    if _FONT_PATH.exists():
        try:
            return ImageFont.truetype(str(_FONT_PATH), size)
        except Exception:
            pass

    # Try system fonts
    for path in [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue

    logger.warning("font_not_found", message="Using Pillow default font. Install Anton-Regular.ttf in assets/fonts/")
    return ImageFont.load_default()


def _wrap_text(text: str, font, draw, max_width: int) -> list:
    words = text.split()
    lines = []
    current = []

    for word in words:
        test_line = " ".join(current + [word])
        try:
            w = draw.textlength(test_line, font=font)
        except Exception:
            w = len(test_line) * 50  # rough fallback
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return lines[:3]  # max 3 lines on thumbnail


def _draw_text_with_stroke(
    draw,
    text: str,
    x: int,
    y: int,
    font,
    fill: str,
    stroke: str,
    stroke_width: int,
) -> None:
    # Draw stroke by offsetting in 8 directions
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke)

    # Draw main text
    draw.text((x, y), text, font=font, fill=fill)
