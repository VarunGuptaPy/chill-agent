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

    _render_thumbnail(raw_image_path, title, path_a, text_align="center")
    _render_thumbnail(raw_image_path, title, path_b, text_align="left")

    logger.info("thumbnails_created", a=str(path_a), b=str(path_b))
    return path_a, path_b


def _render_thumbnail(
    source: Path,
    title: str,
    output: Path,
    text_align: str = "center",
    target_size: Tuple[int, int] = (1280, 720),
) -> None:
    from PIL import Image, ImageDraw

    W, H = target_size
    canvas = Image.new("RGB", (W, H), color=(255, 255, 255))

    # --- Text zone: top 32% of canvas ---
    text_zone_h = int(H * 0.32)
    text_padding = 40

    # --- Image zone: bottom 68% of canvas ---
    img_zone_y = text_zone_h
    img_zone_h = H - text_zone_y
    img_zone_w = W

    source_img = Image.open(str(source)).convert("RGBA")

    # Scale image to fit bottom zone, preserve aspect ratio
    src_w, src_h = source_img.size
    scale = min(img_zone_w / src_w, img_zone_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    source_img = source_img.resize((new_w, new_h), Image.LANCZOS)

    # If image has white/near-white background, paste directly; otherwise center it
    img_x = (W - new_w) // 2
    img_y = img_zone_y + (img_zone_h - new_h) // 2

    # Composite onto white canvas (handles RGBA transparency)
    bg = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    bg.paste(source_img, (img_x, img_y), source_img if source_img.mode == "RGBA" else None)
    canvas = bg.convert("RGB")

    draw = ImageDraw.Draw(canvas)

    # --- Draw title text in text zone ---
    available_w = W - text_padding * 2

    # Find font size that fits within text zone height
    font_size = 90
    font = _load_font(font_size)
    while font_size > 28:
        lines = _wrap_text(title.upper(), font, draw, max_width=available_w)
        line_height = int(font_size * 1.15)
        total_h = len(lines) * line_height
        if total_h <= text_zone_h - text_padding:
            break
        font_size -= 4
        font = _load_font(font_size)

    lines = _wrap_text(title.upper(), font, draw, max_width=available_w)
    line_height = int(font_size * 1.15)
    total_text_h = len(lines) * line_height

    # Center text vertically within text zone
    start_y = (text_zone_h - total_text_h) // 2

    for line in lines:
        try:
            line_w = int(draw.textlength(line, font=font))
        except Exception:
            line_w = int(len(line) * font_size * 0.6)

        if text_align == "center":
            x = (W - line_w) // 2
        else:
            x = text_padding

        _draw_text_with_stroke(
            draw, line, x, start_y, font,
            fill=(15, 15, 15),
            stroke=(255, 255, 255),
            stroke_width=3,
        )
        start_y += line_height

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output), "JPEG", quality=95)


def _load_font(size: int):
    from PIL import ImageFont

    if _FONT_PATH.exists():
        try:
            return ImageFont.truetype(str(_FONT_PATH), size)
        except Exception:
            pass

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
            w = len(test_line) * 50
        if w <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]

    if current:
        lines.append(" ".join(current))

    return lines[:3]


def _draw_text_with_stroke(
    draw,
    text: str,
    x: int,
    y: int,
    font,
    fill,
    stroke,
    stroke_width: int,
) -> None:
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke)
    draw.text((x, y), text, font=font, fill=fill)
