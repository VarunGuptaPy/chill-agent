"""Stage 7: Thumbnail — overlays bold title text on the generated image."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

import structlog

logger = structlog.get_logger()

_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"

# Top gradient bar covers top 30% of image for text readability
_GRADIENT_HEIGHT_RATIO = 0.30


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

    _render_thumbnail(raw_image_path, overlay_text, path_a, variant="a")
    _render_thumbnail(raw_image_path, overlay_text, path_b, variant="b")

    logger.info("thumbnails_created", a=str(path_a), b=str(path_b))
    return path_a, path_b


def _render_thumbnail(
    source: Path,
    text: str,
    output: Path,
    variant: str = "a",
    target_size: Tuple[int, int] = (1280, 720),
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(str(source)).convert("RGB")
    img = img.resize(target_size, Image.LANCZOS)

    w, h = target_size
    gradient_h = int(h * _GRADIENT_HEIGHT_RATIO)

    # Draw semi-transparent dark gradient bar at top
    overlay = Image.new("RGBA", (w, gradient_h), (0, 0, 0, 0))
    draw_ov = ImageDraw.Draw(overlay)
    for y in range(gradient_h):
        # Opacity: 180 at top, 0 at bottom (fade out)
        alpha = int(180 * (1.0 - y / gradient_h))
        draw_ov.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    img_rgba = img.convert("RGBA")
    img_rgba.paste(overlay, (0, 0), overlay)
    img = img_rgba.convert("RGB")

    draw = ImageDraw.Draw(img)

    # Auto-scale font to fit within top gradient area
    max_font_size = int(gradient_h * 0.55)
    font_size = max(28, min(max_font_size, 90))
    font = _load_font(font_size)

    # Shrink font until text fits in 90% of width
    max_text_width = int(w * 0.90)
    while font_size > 24:
        lines = _wrap_text(text, font, draw, max_width=max_text_width)
        line_height = font_size + 8
        total_h = len(lines) * line_height
        if total_h <= gradient_h - 10:
            break
        font_size -= 4
        font = _load_font(font_size)

    lines = _wrap_text(text, font, draw, max_width=max_text_width)
    line_height = font_size + 8
    total_text_height = len(lines) * line_height

    # Center text horizontally; place in top gradient zone
    # variant "b" shifts text slightly right for A/B variety
    y_start = max(8, (gradient_h - total_text_height) // 2)

    for line in lines:
        try:
            line_w = draw.textlength(line, font=font)
        except Exception:
            line_w = len(line) * font_size * 0.6
        if variant == "b":
            x = min(int(w * 0.55), w - int(line_w) - 20)
        else:
            x = max(20, (w - int(line_w)) // 2)
        _draw_text_with_stroke(draw, line, x, y_start, font, fill="white", stroke="black", stroke_width=3)
        y_start += line_height

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
