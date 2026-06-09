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
    from PIL import Image, ImageDraw

    W, H = target_size
    canvas = Image.new("RGB", (W, H), color=(255, 255, 255))

    # Layout: text zone on left (45%), image on right (50%), small margins
    # variant "b" flips: image on left, text on right
    img_w = int(W * 0.50)
    img_h = int(H * 0.78)
    padding = 30

    source_img = Image.open(str(source)).convert("RGB")
    source_img.thumbnail((img_w, img_h), Image.LANCZOS)
    actual_w, actual_h = source_img.size

    if variant == "b":
        img_x = padding
        text_zone_x = img_w + padding * 2
    else:
        img_x = W - actual_w - padding
        text_zone_x = padding

    img_y = (H - actual_h) // 2
    canvas.paste(source_img, (img_x, img_y))

    draw = ImageDraw.Draw(canvas)
    text_zone_w = W - img_w - padding * 3

    # Start font at 72, shrink until text fits in text zone
    font_size = 72
    font = _load_font(font_size)
    while font_size > 28:
        lines = _wrap_text(text, font, draw, max_width=text_zone_w)
        line_height = font_size + 10
        total_h = len(lines) * line_height
        if total_h <= H - padding * 2:
            break
        font_size -= 4
        font = _load_font(font_size)

    lines = _wrap_text(text, font, draw, max_width=text_zone_w)
    line_height = font_size + 10
    total_text_h = len(lines) * line_height
    y = (H - total_text_h) // 2

    for line in lines:
        try:
            line_w = draw.textlength(line, font=font)
        except Exception:
            line_w = len(line) * font_size * 0.6
        x = text_zone_x + max(0, (text_zone_w - int(line_w)) // 2)
        _draw_text_with_stroke(draw, line, x, y, font, fill=(20, 20, 20), stroke=(200, 200, 200), stroke_width=2)
        y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output), "JPEG", quality=95)


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
