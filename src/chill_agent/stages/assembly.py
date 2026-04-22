"""Stage 6: Video assembly — Ken Burns clips + narration + music + optional captions."""

from __future__ import annotations

import shutil
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
    srt_path,
    video_dir,
)

logger = structlog.get_logger()

_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"

# Ken Burns clip duration targets (seconds per individual clip)
_TARGET_CLIP_SECS = 10.0
_MIN_CLIP_SECS = 4.0
_MAX_CLIP_SECS = 20.0


def assemble_video(
    run_id: str,
    output_root: Path,
    tts_result: TTSResult,
    segment_image_paths: List[List[Path]],  # outer=segment, inner=images
    alignment: AlignmentResult,
    segment_numbers: Optional[List[int]] = None,  # countdown numbers [7,6,...,1]
    music_dir: Optional[Path] = None,
    enable_captions: bool = True,
    force: bool = False,
) -> Path:
    """Build the final MP4 from images, audio, music, and optional captions."""

    final_path = final_video_path(output_root, run_id)
    if final_path.exists() and not force:
        logger.info("assembly_cache_hit", path=str(final_path))
        return final_path

    raw_video = video_dir(output_root, run_id) / "concat_raw.mp4"
    with_voice = video_dir(output_root, run_id) / "with_voice.mp4"

    # Step 1+2: Build Ken Burns clips and concatenate.
    # Skipped when concat_raw.mp4 already exists (and force is not set) so that
    # re-running only the mux step is fast.
    if not raw_video.exists() or force:
        effective_seg_nums = segment_numbers or list(range(1, len(segment_image_paths) + 1))
        all_clips = _build_all_clips(
            run_id=run_id,
            output_root=output_root,
            segment_image_paths=segment_image_paths,
            alignment=alignment,
            tts_result=tts_result,
            segment_numbers=effective_seg_nums,
            force=force,
        )
        logger.info("assembly_concat", clips=len(all_clips))
        concat_video_clips(all_clips, raw_video)
    else:
        logger.info("assembly_concat_cache_hit", path=str(raw_video))

    # Step 3: Mux with narration audio.
    # Skipped when with_voice.mp4 already exists (and force is not set).
    if not with_voice.exists() or force:
        logger.info("assembly_mux_voice")
        mux_video_audio(raw_video, tts_result.full_audio_path, with_voice)
    else:
        logger.info("assembly_mux_cache_hit", path=str(with_voice))

    current = with_voice

    # Step 4: Mix background music (optional)
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

    shutil.copy2(str(current), str(final_path))
    logger.info("assembly_done", path=str(final_path))
    return final_path


def _build_all_clips(
    run_id: str,
    output_root: Path,
    segment_image_paths: List[List[Path]],
    alignment: AlignmentResult,
    tts_result: TTSResult,
    segment_numbers: List[int],
    force: bool,
) -> List[Path]:
    """Build Ken Burns clips for all segments, cycling through images."""

    all_clips: List[Path] = []
    global_clip_idx = 0

    for seg_pos, (img_paths, seg_num) in enumerate(zip(segment_image_paths, segment_numbers)):
        seg_duration = _get_segment_duration(seg_num, seg_pos, alignment, tts_result)
        if seg_duration < 1.0:
            seg_duration = 5.0

        n_unique = len(img_paths)

        # Prefer showing each unique image exactly once at a comfortable hold duration.
        # Only cycle images if the segment is so long that each image would exceed MAX_CLIP_SECS.
        base_clip_dur = seg_duration / n_unique
        if base_clip_dur <= _MAX_CLIP_SECS:
            # All unique images fit without repeating — ideal path
            n_clips = n_unique
            clip_duration = max(_MIN_CLIP_SECS, base_clip_dur)
        else:
            # Segment is very long; need more clips than unique images, so some will cycle
            n_clips = max(n_unique, round(seg_duration / _TARGET_CLIP_SECS))
            clip_duration = seg_duration / n_clips
            clip_duration = max(_MIN_CLIP_SECS, min(_MAX_CLIP_SECS, clip_duration))

        logger.info(
            "assembly_segment_clips",
            seg_num=seg_num,
            seg_duration=round(seg_duration, 2),
            n_unique_images=n_unique,
            n_clips=n_clips,
            clip_duration=round(clip_duration, 2),
            cycling=n_clips > n_unique,
        )

        for clip_i in range(n_clips):
            img_path = img_paths[clip_i % n_unique]
            clip_path = video_dir(output_root, run_id) / f"clip_{global_clip_idx:03d}.mp4"
            global_clip_idx += 1

            if clip_path.exists() and not force:
                logger.debug("assembly_clip_cache_hit", clip=global_clip_idx - 1)
                all_clips.append(clip_path)
                continue

            build_ken_burns_clip(
                image_path=img_path,
                output_path=clip_path,
                duration=clip_duration,
                mode_idx=global_clip_idx,
            )
            all_clips.append(clip_path)

    return all_clips


def _get_segment_duration(
    seg_num: int,
    seg_pos: int,
    alignment: AlignmentResult,
    tts_result: TTSResult,
) -> float:
    """Get segment duration. Prefers alignment if valid, falls back to TTS duration."""
    for seg in alignment.segments:
        if seg.segment_idx == seg_num:
            dur = seg.end_sec - seg.start_sec
            if dur >= 1.0:
                return dur

    # Alignment timestamps are invalid/zeroed — use actual TTS segment duration
    if seg_pos < len(tts_result.per_segment_durations):
        return tts_result.per_segment_durations[seg_pos]

    n = max(len(tts_result.per_segment_durations), 1)
    return tts_result.total_duration_seconds / n
