"""Stage 6: Video assembly — Ken Burns clips + narration + music + optional captions.

Video layout:
  [intro clip: Gemini-generated character — 2.5s silent visual beat]
  [segment clips: Ken Burns pan/zoom over generated images]
  [outro clip: stick figure "That's all for this video..."]
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.media.alignment import AlignmentResult
from chill_agent.media.ffmpeg_ops import (
    build_ken_burns_clip,
    build_number_card_clip,
    burn_captions,
    concat_video_clips,
    mix_music,
    mux_video_audio,
)
from chill_agent.media.music import pick_music_track
from chill_agent.media.stick_figure import ensure_intro_frame, ensure_outro_frame
from chill_agent.stages.tts import TTSResult
from chill_agent.utils.paths import (
    ass_path,
    final_video_path,
    srt_path,
    video_dir,
)

logger = structlog.get_logger()

_FONT_PATH = Path(__file__).parent.parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"
_ASSETS_DIR = Path(__file__).parent.parent.parent.parent / "assets"

# Ken Burns clip duration targets (seconds per individual clip)
_TARGET_CLIP_SECS = 10.0
_MIN_CLIP_SECS = 4.0
_MAX_CLIP_SECS = 20.0

# Duration of the number transition card shown before each segment
_NUMBER_CARD_SECS = 1.5


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

    if not with_voice.exists() or force:
        logger.info("assembly_mux_voice")
        mux_video_audio(raw_video, tts_result.full_audio_path, with_voice)
    else:
        logger.info("assembly_mux_cache_hit", path=str(with_voice))

    current = with_voice

    if music_dir:
        music_track = pick_music_track(music_dir)
        if music_track:
            with_music = video_dir(output_root, run_id) / "with_music.mp4"
            logger.info("assembly_mix_music", track=music_track.name)
            mix_music(current, music_track, with_music, music_volume=0.12)
            current = with_music

    # Prefer ASS karaoke over plain SRT
    _ass_file = ass_path(output_root, run_id)
    _srt_file = srt_path(output_root, run_id)
    caption_file = _ass_file if _ass_file.exists() else (_srt_file if _srt_file.exists() else None)
    if enable_captions and caption_file and alignment.srt_content:
        with_captions = video_dir(output_root, run_id) / "with_captions.mp4"
        font = _FONT_PATH if _FONT_PATH.exists() else None
        logger.info("assembly_burn_captions", format=caption_file.suffix)
        burn_captions(current, caption_file, with_captions, font_path=font)
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
    """Build all clips: [intro] + [segment Ken Burns clips] + [outro]."""

    vdir = video_dir(output_root, run_id)
    all_clips: List[Path] = []
    global_clip_idx = 0

    # ── Intro clip ────────────────────────────────────────────────────────────
    intro_frame = ensure_intro_frame(_ASSETS_DIR)
    intro_dur = max(tts_result.intro_duration, 2.0)
    intro_clip = vdir / "clip_intro.mp4"
    if not intro_clip.exists() or force:
        logger.info("assembly_build_intro_clip", duration=round(intro_dur, 2))
        build_ken_burns_clip(
            image_path=intro_frame,
            output_path=intro_clip,
            duration=intro_dur,
            mode_idx=0,  # zoom_in — gentle open
        )
    else:
        logger.debug("assembly_intro_clip_cache_hit")
    all_clips.append(intro_clip)

    # ── Segment clips ─────────────────────────────────────────────────────────
    for seg_pos, (img_paths, seg_num) in enumerate(zip(segment_image_paths, segment_numbers)):
        seg_duration = _get_segment_duration(seg_num, seg_pos, alignment, tts_result)
        if seg_duration < 1.0:
            seg_duration = 5.0

        # Number card — deduct its duration from the segment budget so total video
        # duration stays in sync with the audio track.
        card_dur = min(_NUMBER_CARD_SECS, seg_duration * 0.08)
        num_card_path = vdir / f"clip_num_{seg_num:02d}.mp4"
        if not num_card_path.exists() or force:
            logger.info("assembly_build_number_card", seg_num=seg_num, duration=round(card_dur, 2))
            build_number_card_clip(seg_num, num_card_path, duration=card_dur)
        else:
            logger.debug("assembly_number_card_cache_hit", seg_num=seg_num)
        all_clips.append(num_card_path)

        # Remaining duration for Ken Burns clips
        remaining = seg_duration - card_dur

        n_unique = len(img_paths)
        base_clip_dur = remaining / n_unique
        if base_clip_dur <= _MAX_CLIP_SECS:
            n_clips = n_unique
            clip_duration = max(_MIN_CLIP_SECS, base_clip_dur)
        else:
            n_clips = max(n_unique, round(remaining / _TARGET_CLIP_SECS))
            clip_duration = remaining / n_clips
            clip_duration = max(_MIN_CLIP_SECS, min(_MAX_CLIP_SECS, clip_duration))

        logger.info(
            "assembly_segment_clips",
            seg_num=seg_num,
            seg_duration=round(seg_duration, 2),
            card_dur=round(card_dur, 2),
            remaining=round(remaining, 2),
            n_unique_images=n_unique,
            n_clips=n_clips,
            clip_duration=round(clip_duration, 2),
            cycling=n_clips > n_unique,
        )

        for clip_i in range(n_clips):
            img_path = img_paths[clip_i % n_unique]
            clip_path = vdir / f"clip_{global_clip_idx:03d}.mp4"
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

    # ── Outro clip ────────────────────────────────────────────────────────────
    outro_frame = ensure_outro_frame(_ASSETS_DIR)
    outro_dur = max(tts_result.outro_duration, 3.0)
    outro_clip = vdir / "clip_outro.mp4"
    if not outro_clip.exists() or force:
        logger.info("assembly_build_outro_clip", duration=round(outro_dur, 2))
        build_ken_burns_clip(
            image_path=outro_frame,
            output_path=outro_clip,
            duration=outro_dur,
            mode_idx=1,  # zoom_out — gentle close
        )
    else:
        logger.debug("assembly_outro_clip_cache_hit")
    all_clips.append(outro_clip)

    return all_clips


def _get_segment_duration(
    seg_num: int,
    seg_pos: int,
    alignment: AlignmentResult,
    tts_result: TTSResult,
) -> float:
    """Get segment duration from TTS (ground truth — each segment synthesized individually)."""
    if seg_pos < len(tts_result.per_segment_durations):
        dur = tts_result.per_segment_durations[seg_pos]
        if dur >= 1.0:
            return dur

    for seg in alignment.segments:
        if seg.segment_idx == seg_num:
            dur = seg.end_sec - seg.start_sec
            if dur >= 1.0:
                return dur

    n = max(len(tts_result.per_segment_durations), 1)
    return tts_result.total_duration_seconds / n
