"""Generate intro and outro frames (created once, reused for every video).

Intro: Gemini-generated character image (falls back to PIL stick figure).
Outro: PIL stick figure with subscribe CTA.
"""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

_OUTRO_TEXT = "That's all for this video, I will be making similar\nkind of video in future.\nSubscribe to stay updated."

_INTRO_PROMPT = (
    "A chill, relaxed cartoon character with a warm smile and friendly wave, "
    "flat cartoon illustration style, bold black outlines, vibrant limited color palette, "
    "centered on a warm cream background, clean composition, flat shading no gradients, "
    "quirky charming expression, 16:9 aspect ratio, no text"
)

_SKIN = (180, 120, 60)       # warm brown skin
_OUTLINE = (30, 30, 30)      # near-black for all lines/outlines
_BG = (248, 244, 232)        # warm cream background
_BUBBLE_BG = (255, 255, 255)
_BUBBLE_BORDER = (40, 40, 40)
_TEXT_COLOR = (20, 20, 20)
_ACCENT = (220, 60, 40)      # red accent for subscribe CTA (outro only)

_W, _H = 1920, 1080


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load Anton font if available, fall back to system fonts, then Pillow default."""
    font_candidates = [
        Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf",
        Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Bebas-Regular.ttf",
        # macOS system fonts
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/System/Library/Fonts/Geneva.ttf"),
        # Linux common
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    for p in font_candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_stick_figure(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 1.0) -> None:
    """Draw a brown-skin stick figure centered at (cx, cy)."""
    lw = max(5, int(7 * scale))

    # Head
    hr = int(80 * scale)
    head_cx, head_cy = cx, cy - int(230 * scale)
    draw.ellipse(
        [head_cx - hr, head_cy - hr, head_cx + hr, head_cy + hr],
        fill=_SKIN, outline=_OUTLINE, width=lw,
    )

    # Eyes
    eo = int(28 * scale)
    er = int(9 * scale)
    for ex in [head_cx - eo, head_cx + eo]:
        draw.ellipse([ex - er, head_cy - er, ex + er, head_cy + er], fill=_OUTLINE)

    # Smile
    draw.arc(
        [head_cx - int(30 * scale), head_cy + int(15 * scale),
         head_cx + int(30 * scale), head_cy + int(45 * scale)],
        start=0, end=180, fill=_OUTLINE, width=lw - 1,
    )

    # Neck + torso
    neck_top = head_cy + hr
    body_bottom = cy + int(100 * scale)
    draw.line([(cx, neck_top), (cx, body_bottom)], fill=_OUTLINE, width=lw)

    # Arms (raised slightly — friendly gesture)
    arm_y = cy - int(80 * scale)
    draw.line([(cx, arm_y), (cx - int(130 * scale), arm_y - int(40 * scale))], fill=_OUTLINE, width=lw)
    draw.line([(cx, arm_y), (cx + int(130 * scale), arm_y - int(40 * scale))], fill=_OUTLINE, width=lw)

    # Legs
    draw.line([(cx, body_bottom), (cx - int(90 * scale), cy + int(250 * scale))], fill=_OUTLINE, width=lw)
    draw.line([(cx, body_bottom), (cx + int(90 * scale), cy + int(250 * scale))], fill=_OUTLINE, width=lw)


def _draw_speech_bubble(
    draw: ImageDraw.ImageDraw,
    text: str,
    tip_x: int,
    tip_y: int,
    direction: str = "left",  # which side the tail points toward ("left"=figure is left of bubble)
    font_size: int = 52,
    max_chars: int = 28,
    accent_last_line: bool = False,
) -> None:
    """Draw a rounded speech bubble with text above the figure."""
    font = _load_font(font_size)
    lines = text.split("\n")

    padding = 40
    line_spacing = int(font_size * 1.35)

    # Measure lines
    widths = []
    for line in lines:
        bb = font.getbbox(line)
        widths.append(bb[2] - bb[0])
    max_w = max(widths) if widths else 200
    box_w = max_w + padding * 2
    box_h = len(lines) * line_spacing + padding * 2

    # Position bubble centered horizontally above figure tip
    bx = tip_x - box_w // 2
    by = tip_y - box_h - 60  # 60px gap for tail

    # Clamp to canvas
    bx = max(20, min(_W - box_w - 20, bx))
    by = max(20, by)

    # Bubble rectangle
    r = 20
    draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=r,
                            fill=_BUBBLE_BG, outline=_BUBBLE_BORDER, width=4)

    # Tail triangle pointing down toward figure
    tail_bx = tip_x
    draw.polygon(
        [(tail_bx - 18, by + box_h), (tail_bx + 18, by + box_h), (tip_x, tip_y)],
        fill=_BUBBLE_BG,
    )
    # Tail border
    draw.line([(tail_bx - 18, by + box_h), (tip_x, tip_y)], fill=_BUBBLE_BORDER, width=4)
    draw.line([(tail_bx + 18, by + box_h), (tip_x, tip_y)], fill=_BUBBLE_BORDER, width=4)

    # Text inside bubble
    for i, line in enumerate(lines):
        tx = bx + padding
        ty = by + padding + i * line_spacing
        color = _ACCENT if (accent_last_line and i == len(lines) - 1) else _TEXT_COLOR
        draw.text((tx, ty), line, font=font, fill=color)


def _render_frame(text: str, output_path: Path, accent_last: bool = False) -> None:
    img = Image.new("RGB", (_W, _H), color=_BG)
    draw = ImageDraw.Draw(img)

    # Subtle grid lines for background texture
    for x in range(0, _W, 60):
        draw.line([(x, 0), (x, _H)], fill=(235, 230, 218), width=1)
    for y in range(0, _H, 60):
        draw.line([(0, y), (_W, y)], fill=(235, 230, 218), width=1)

    # Figure position: lower-center
    fig_cx = _W // 2
    fig_cy = _H // 2 + 150

    # Speech bubble tip: just above the figure's head
    bubble_tip_x = fig_cx
    bubble_tip_y = fig_cy - int(230 * 1.0) - 80 - 10  # just above head top

    _draw_speech_bubble(
        draw, text,
        tip_x=bubble_tip_x,
        tip_y=bubble_tip_y,
        accent_last_line=accent_last,
    )

    _draw_stick_figure(draw, fig_cx, fig_cy, scale=1.0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")


def _generate_intro_frame_gemini(output_path: Path) -> bool:
    """Try to generate the intro frame via Vertex AI. Returns True on success."""
    key_file = os.environ.get("VERTEX_AI_KEY_FILE", "keys/dubmanandyoutube.json")
    project = os.environ.get("VERTEX_AI_PROJECT", "dubmanandyoutube")
    location = os.environ.get("VERTEX_AI_LOCATION", "us-central1")
    model = os.environ.get("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-001")

    if not Path(key_file).exists():
        return False
    try:
        from google import genai
        from google.genai import types
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            credentials=credentials,
        )
        if "imagen" in model.lower():
            response = client.models.generate_images(
                model=model,
                prompt=_INTRO_PROMPT,
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="16:9"),
            )
            if response.generated_images:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.generated_images[0].image.image_bytes)
                return True
        else:
            response = client.models.generate_content(
                model=model,
                contents=_INTRO_PROMPT,
                config=types.GenerateContentConfig(
                    response_modalities=["image", "text"],
                    image_config=types.ImageConfig(aspect_ratio="16:9"),
                ),
            )
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(part.inline_data.data)
                        return True
    except Exception:
        pass
    return False


_CHILL_DUDE_IMAGE = Path(__file__).parent.parent.parent.parent / "assets" / "chill_dude.png"


def _get_chill_dude(target: Path) -> Path:
    """Return the static chill dude image, scaled to 1920x1080."""
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    img = Image.open(_CHILL_DUDE_IMAGE).convert("RGB")
    img = img.resize((_W, _H), Image.LANCZOS)
    img.save(str(target), "PNG")
    return target


def ensure_intro_frame(assets_dir: Path) -> Path:
    return _get_chill_dude(assets_dir / "intro_frame.png")


def ensure_outro_frame(assets_dir: Path) -> Path:
    return _get_chill_dude(assets_dir / "outro_frame.png")


OUTRO_TEXT = "That's all for this video, I will be making similar kind of video in future. Subscribe to stay updated."
INTRO_TEXT = "Let's get right into it."
