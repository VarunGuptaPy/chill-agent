"""Stage 6: Video assembly — Ken Burns clips + narration + music + optional captions."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.media.alignment import AlignmentResult
from chill_agent.media.ffmpeg_ops import (
    build_ken_burns_clip,
    burn_captions,
    concat_video_clips,
    mix_music,
    mux_video_audio,
)
from chill_agent.media.music import pick_music_track
from chill_agent.stages.tts import TTSResult
from chill_agent.utils.paths import (
    final_video_path,
    segment_video_path,
    srt_path,
    video_dir,
)

logger = structlog.get_logger()

_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"


def assemble_video(
    run_id: str,
    output_root: Path,
    tts_result: TTSResult,
    segment_image_paths: List[Path],
    alignment: AlignmentResult,
    music_dir: Optional[Path] = None,
    enable_captions: bool = True,
    force: bool = False,
) -> Path:
    """Build the final MP4 from images, audio, music, and optional captions."""

    final_path = final_video_path(output_root, run_id)
    if final_path.exists() and not force:
        logger.info("assembly_cache_hit", path=str(final_path))
        return final_path

    # Step 1: Build per-segment Ken Burns clips
    seg_clips = _build_segment_clips(
        run_id=run_id,
        output_root=output_root,
        image_paths=segment_image_paths,
        alignment=alignment,
        tts_result=tts_result,
        force=force,
    )

    # Step 2: Concatenate clips
    raw_video = video_dir(output_root, run_id) / "concat_raw.mp4"
    logger.info("assembly_concat", clips=len(seg_clips))
    concat_video_clips(seg_clips, raw_video)

    # Step 3: Mux with narration audio
    with_voice = video_dir(output_root, run_id) / "with_voice.mp4"
    logger.info("assembly_mux_voice")
    mux_video_audio(raw_video, tts_result.full_audio_path, with_voice)

    current = with_voice

    # Step 4: Mix in background music (optional)
    if music_dir:
        music_track = pick_music_track(music_dir)
        if music_track:
            with_music = video_dir(output_root, run_id) / "with_music.mp4"
            logger.info("assembly_mix_music", track=music_track.name)
            mix_music(current, music_track, with_music, music_volume=0.12)
            current = with_music

    # Step 5: Burn captions (optional)
    srt_file = srt_path(output_root, run_id)
    if enable_captions and srt_file.exists() and alignment.srt_content:
        with_captions = video_dir(output_root, run_id) / "with_captions.mp4"
        font = _FONT_PATH if _FONT_PATH.exists() else None
        logger.info("assembly_burn_captions")
        burn_captions(current, srt_file, with_captions, font_path=font)
        current = with_captions

    # Step 6: Final copy to canonical output path
    import shutil
    shutil.copy2(str(current), str(final_path))

    logger.info("assembly_done", path=str(final_path))
    return final_path


def _build_segment_clips(
    run_id: str,
    output_root: Path,
    image_paths: List[Path],
    alignment: AlignmentResult,
    tts_result: TTSResult,
    force: bool,
) -> List[Path]:
    """Build one Ken Burns clip per segment."""

    clips = []
    n = len(image_paths)

    for i, img_path in enumerate(image_paths):
        clip_path = segment_video_path(output_root, run_id, i)

        if clip_path.exists() and not force:
            logger.debug("assembly_clip_cache_hit", segment=i)
            clips.append(clip_path)
            continue

        # Get duration from alignment or TTS result
        duration = _get_segment_duration(i, alignment, tts_result)
        if duration < 1.0:
            duration = 5.0  # fallback minimum

        logger.info(
            "assembly_build_clip",
            segment=i,
            duration=round(duration, 2),
            mode_idx=i,
        )

        build_ken_burns_clip(
            image_path=img_path,
            output_path=clip_path,
            duration=duration,
            mode_idx=i,  # cycles: zoom_in, zoom_out, pan_left, pan_right
        )
        clips.append(clip_path)

    return clips


def _get_segment_duration(
    segment_idx: int,
    alignment: AlignmentResult,
    tts_result: TTSResult,
) -> float:
    """Get the duration for a segment from alignment data or TTS result."""

    # Try alignment first (more accurate)
    for seg in alignment.segments:
        if seg.segment_idx == segment_idx + 1:  # segments are 1-indexed in alignment
            return seg.end_sec - seg.start_sec

    # Fall back to TTS per-segment duration
    if segment_idx < len(tts_result.per_segment_durations):
        return tts_result.per_segment_durations[segment_idx]

    # Last fallback: divide total by count
    n = max(len(tts_result.per_segment_durations), 1)
    return tts_result.total_duration_seconds / n
