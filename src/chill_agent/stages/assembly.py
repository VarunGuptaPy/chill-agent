"""Stage 6: Video assembly — Ken Burns clips + narration + music + optional captions."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.media.alignment import AlignmentResult, get_image_switch_times
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

# Per-image display time constraints
_MIN_IMAGE_SECS = 3.0
_MAX_IMAGE_SECS = 8.0


def assemble_video(
    run_id: str,
    output_root: Path,
    tts_result: TTSResult,
    segment_image_paths: List[List[Path]],  # outer=segment, inner=images
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

    # Step 1: Build per-image Ken Burns clips (multiple per segment)
    all_clips = _build_all_clips(
        run_id=run_id,
        output_root=output_root,
        segment_image_paths=segment_image_paths,
        alignment=alignment,
        tts_result=tts_result,
        force=force,
    )

    # Step 2: Concatenate all clips into one raw video
    raw_video = video_dir(output_root, run_id) / "concat_raw.mp4"
    logger.info("assembly_concat", clips=len(all_clips))
    concat_video_clips(all_clips, raw_video)

    # Step 3: Mux with narration audio
    with_voice = video_dir(output_root, run_id) / "with_voice.mp4"
    logger.info("assembly_mux_voice")
    mux_video_audio(raw_video, tts_result.full_audio_path, with_voice)

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
    force: bool,
) -> List[Path]:
    """Build one Ken Burns clip per image across all segments."""

    all_clips: List[Path] = []
    global_clip_idx = 0

    for seg_idx, img_paths in enumerate(segment_image_paths):
        seg_duration = _get_segment_duration(seg_idx, alignment, tts_result)
        if seg_duration < 1.0:
            seg_duration = 5.0

        # Get image switch timestamps (natural cut points or even splits)
        switch_times = get_image_switch_times(
            segment_start=_get_segment_start(seg_idx, alignment),
            segment_end=_get_segment_start(seg_idx, alignment) + seg_duration,
            num_images=len(img_paths),
            word_timestamps=alignment.word_timestamps,
        )

        # Cap number of images if segment is too short
        max_imgs = max(1, int(seg_duration / _MIN_IMAGE_SECS))
        active_imgs = img_paths[:max_imgs]

        for img_idx, img_path in enumerate(active_imgs):
            clip_path = video_dir(output_root, run_id) / f"clip_{global_clip_idx:03d}.mp4"
            global_clip_idx += 1

            if clip_path.exists() and not force:
                logger.debug("assembly_clip_cache_hit", clip=global_clip_idx - 1)
                all_clips.append(clip_path)
                continue

            # Duration for this specific image
            if img_idx < len(switch_times) - 1:
                img_duration = switch_times[img_idx + 1] - switch_times[img_idx]
            else:
                img_duration = seg_duration / len(active_imgs)

            # Clamp to reasonable range
            img_duration = max(_MIN_IMAGE_SECS, min(_MAX_IMAGE_SECS, img_duration))

            logger.info(
                "assembly_build_clip",
                seg=seg_idx,
                img=img_idx,
                duration=round(img_duration, 2),
                mode_idx=global_clip_idx,
            )

            build_ken_burns_clip(
                image_path=img_path,
                output_path=clip_path,
                duration=img_duration,
                mode_idx=global_clip_idx,
            )
            all_clips.append(clip_path)

    return all_clips


def _get_segment_duration(
    seg_idx: int,
    alignment: AlignmentResult,
    tts_result: TTSResult,
) -> float:
    # 1-indexed segment_idx in alignment
    for seg in alignment.segments:
        if seg.segment_idx == seg_idx + 1:
            return seg.end_sec - seg.start_sec

    if seg_idx < len(tts_result.per_segment_durations):
        return tts_result.per_segment_durations[seg_idx]

    n = max(len(tts_result.per_segment_durations), 1)
    return tts_result.total_duration_seconds / n


def _get_segment_start(seg_idx: int, alignment: AlignmentResult) -> float:
    for seg in alignment.segments:
        if seg.segment_idx == seg_idx + 1:
            return seg.start_sec
    return 0.0
