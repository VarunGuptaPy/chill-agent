"""FFmpeg operations: Ken Burns, concat, mux, captions, validation."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger()

_KEN_BURNS_MODES = ["zoom_in", "zoom_out", "pan_left", "pan_right"]
_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"


def _run_ffmpeg(args: List[str], description: str = "") -> None:
    cmd = ["ffmpeg", "-y"] + args
    logger.debug("ffmpeg_command", cmd=" ".join(cmd), description=description)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("ffmpeg_failed", stderr=result.stderr[-2000:], cmd=" ".join(cmd))
        raise RuntimeError(f"FFmpeg failed ({description}): {result.stderr[-500:]}")


def build_ken_burns_clip(
    image_path: Path,
    output_path: Path,
    duration: float,
    mode_idx: int = 0,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Build a Ken Burns animated clip from a still image."""
    mode = _KEN_BURNS_MODES[mode_idx % len(_KEN_BURNS_MODES)]
    total_frames = int(duration * fps)

    if mode == "zoom_in":
        # Slow zoom from 1.0x to 1.08x, centered
        zoom_expr = f"1+(0.08*on/{total_frames})"
        x_expr = f"iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)"
    elif mode == "zoom_out":
        # Slow zoom from 1.08x down to 1.0x
        zoom_expr = f"1.08-(0.08*on/{total_frames})"
        x_expr = f"iw/2-(iw/zoom/2)"
        y_expr = f"ih/2-(ih/zoom/2)"
    elif mode == "pan_left":
        # Pan from right to left at 1.05x zoom
        zoom_expr = "1.05"
        x_expr = f"(iw/zoom*0.05)-(iw/zoom*0.05*(on/{total_frames}))"
        y_expr = f"ih/2-(ih/zoom/2)"
    else:  # pan_right
        # Pan from left to right at 1.05x zoom
        zoom_expr = "1.05"
        x_expr = f"iw/zoom*0.05*(on/{total_frames})"
        y_expr = f"ih/2-(ih/zoom/2)"

    zoompan_filter = (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
        f":d={total_frames}:s={width}x{height}:fps={fps}"
    )

    vf = f"{zoompan_filter},format=yuv420p"

    _run_ffmpeg(
        [
            "-loop", "1",
            "-i", str(image_path),
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-profile:v", "high",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            str(output_path),
        ],
        description=f"ken_burns_{mode}",
    )

    return output_path


def build_number_card_clip(
    number: int,
    output_path: Path,
    duration: float = 1.5,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    """Build a short transition card showing a big number (e.g. '7') on a dark background."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(18, 18, 18))
    draw = ImageDraw.Draw(img)

    # Thin horizontal accent lines flanking the number
    line_y_top = int(height * 0.30)
    line_y_bot = int(height * 0.70)
    line_x0, line_x1 = int(width * 0.35), int(width * 0.65)
    draw.line([(line_x0, line_y_top), (line_x1, line_y_top)], fill=(200, 200, 200), width=3)
    draw.line([(line_x0, line_y_bot), (line_x1, line_y_bot)], fill=(200, 200, 200), width=3)

    # Big number
    font_size = int(height * 0.50)
    font = _load_card_font(font_size)
    text = str(number)
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (width - tw) // 2 - bbox[0]
        y = (height - th) // 2 - bbox[1]
    except Exception:
        x, y = width // 2, height // 2

    # Subtle shadow
    draw.text((x + 5, y + 5), text, font=font, fill=(80, 80, 80))
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        tmp_path = Path(tf.name)
    img.save(str(tmp_path))

    try:
        fade_out_start = max(0.0, duration - 0.25)
        vf = (
            f"format=yuv420p,"
            f"fade=t=in:st=0:d=0.2,"
            f"fade=t=out:st={fade_out_start:.2f}:d=0.2"
        )
        _run_ffmpeg(
            [
                "-loop", "1",
                "-i", str(tmp_path),
                "-vf", vf,
                "-t", str(duration),
                "-c:v", "libx264",
                "-profile:v", "high",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-an",
                str(output_path),
            ],
            description=f"number_card_{number}",
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return output_path


def _load_card_font(size: int):
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
    return ImageFont.load_default()


def concat_video_clips(clip_paths: List[Path], output_path: Path) -> Path:
    """Concatenate multiple video clips using concat demuxer."""
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    _run_ffmpeg(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(output_path),
        ],
        description="concat_clips",
    )

    concat_list.unlink(missing_ok=True)
    return output_path


def mux_video_audio(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
) -> Path:
    """Mux video with narration audio. Audio is authoritative for duration.

    We do NOT use -shortest so the audio is never truncated when the video is
    a few seconds shorter (inter-segment silences are in the WAV but not in
    the video clips). The last video frame will freeze briefly, which is fine.
    """
    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            str(output_path),
        ],
        description="mux_video_audio",
    )
    return output_path


def mix_music(
    video_path: Path,
    music_path: Path,
    output_path: Path,
    music_volume: float = 0.12,
) -> Path:
    """Mix background music into video at given volume level."""
    # amix: voice at 1.0, music at music_volume
    # Music is looped to match video duration
    duration_info = probe_duration(video_path)

    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-stream_loop", "-1",
            "-i", str(music_path),
            "-filter_complex",
            f"[0:a]volume=1.0[voice];"
            f"[1:a]volume={music_volume}[music];"
            f"[voice][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-t", str(duration_info),
            str(output_path),
        ],
        description="mix_music",
    )
    return output_path


def burn_captions(
    video_path: Path,
    caption_path: Path,
    output_path: Path,
    font_path: Optional[Path] = None,
) -> Path:
    """Burn captions into video. Supports ASS karaoke (.ass) and plain SRT (.srt)."""
    is_ass = caption_path.suffix.lower() == ".ass"

    if is_ass:
        # ASS karaoke — use embedded styles, only add fontsdir so Anton loads
        base = f"subtitles={caption_path.resolve()}"
        if font_path and font_path.parent.exists():
            base += f":fontsdir={font_path.parent}"
        subs_filter = base
        description = "burn_ass_karaoke"
    else:
        # Plain SRT fallback with manual styling
        style = (
            "FontSize=22,PrimaryColour=&Hffffff,OutlineColour=&H000000,"
            "BorderStyle=1,Outline=2,Shadow=1,Alignment=2"
        )
        subs_filter = f"subtitles={caption_path.resolve()}:force_style='{style}'"
        description = "burn_srt_captions"

    _run_ffmpeg(
        [
            "-i", str(video_path),
            "-vf", subs_filter,
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "libx264",
            "-profile:v", "high",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(output_path),
        ],
        description=description,
    )
    return output_path


def probe_duration(video_path: Path) -> float:
    """Use ffprobe to get video duration in seconds."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    import json

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def probe_has_audio(video_path: Path) -> bool:
    """Check if video has at least one audio stream."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-select_streams", "a",
            str(video_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    import json

    data = json.loads(result.stdout)
    return len(data.get("streams", [])) > 0


def validate_video(video_path: Path) -> None:
    """Validate final MP4 before upload. Raises ValueError if invalid."""
    duration = probe_duration(video_path)
    has_audio = probe_has_audio(video_path)

    if duration < 180:
        raise ValueError(f"Video too short: {duration:.1f}s (minimum 180s)")
    if duration > 1200:
        raise ValueError(f"Video too long: {duration:.1f}s (maximum 1200s)")
    if not has_audio:
        raise ValueError("Video has no audio track")

    logger.info("video_validated", duration=duration, has_audio=has_audio)


def concat_audio_files_with_silence(
    audio_paths: List[Path],
    output_path: Path,
    silence_sec: float = 0.8,
    sample_rate: int = 44100,
) -> Path:
    """Concatenate multiple audio files with silence gaps between them."""
    if not audio_paths:
        raise ValueError("No audio files to concatenate")

    # Build filter_complex: alternate audio segments with silence
    inputs = []
    filter_parts = []

    for i, ap in enumerate(audio_paths):
        inputs.extend(["-i", str(ap)])
        filter_parts.append(f"[{i}:a]")

    n = len(audio_paths)

    # Build the concat filter — insert silence between segments
    # We use aevalsrc to generate silence
    filter_complex_parts = []
    concat_inputs = []

    for i in range(n):
        filter_complex_parts.append(f"[{i}:a]aresample={sample_rate}[a{i}]")
        concat_inputs.append(f"[a{i}]")
        if i < n - 1:
            silence_label = f"[sil{i}]"
            filter_complex_parts.append(
                f"aevalsrc=0:d={silence_sec}:s={sample_rate}:c=stereo{silence_label}"
            )
            concat_inputs.append(silence_label)

    total_inputs = len(concat_inputs)
    concat_filter = "".join(concat_inputs) + f"concat=n={total_inputs}:v=0:a=1[out]"
    filter_complex_parts.append(concat_filter)

    filter_complex = ";".join(filter_complex_parts)

    cmd = inputs + [
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        "-ar", str(sample_rate),
        str(output_path),
    ]

    _run_ffmpeg(cmd, description="concat_audio_with_silence")
    return output_path
