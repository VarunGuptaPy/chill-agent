"""Stage 3: TTS — synthesize narration per segment, stitch with silence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

import structlog

from chill_agent.media.ffmpeg_ops import concat_audio_files_with_silence
from chill_agent.services.tts.base import AudioResult, TTSProvider
from chill_agent.stages.script import Script
from chill_agent.utils.paths import audio_dir, full_audio_path, segment_audio_path

logger = structlog.get_logger()


@dataclass
class TTSResult:
    segment_audio_paths: List[Path]
    full_audio_path: Path
    total_duration_seconds: float
    total_chars: int
    per_segment_durations: List[float]


def synthesize_voice(
    tts: TTSProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    voice_id: str,
    force: bool = False,
) -> TTSResult:
    """Synthesize narration for each segment and stitch into a single WAV."""

    full_audio = full_audio_path(output_root, run_id)

    # Idempotency: if full audio already exists, load segment durations and return
    if full_audio.exists() and not force:
        logger.info("tts_cache_hit", full_audio=str(full_audio))
        return _load_cached(script, run_id, output_root, full_audio)

    seg_paths = []
    seg_durations = []
    total_chars = 0

    for i, seg in enumerate(script.segments):
        out_path = segment_audio_path(output_root, run_id, i)

        if out_path.exists() and not force:
            logger.debug("tts_segment_cache_hit", segment=i, path=str(out_path))
        else:
            logger.info("tts_synthesizing_segment", segment=i, label=seg.label, chars=len(seg.narration))
            tts.synthesize(text=seg.narration, voice_id=voice_id, output_path=out_path)

        seg_paths.append(out_path)
        total_chars += len(seg.narration)

        # Measure duration
        try:
            from pydub import AudioSegment as PyAudioSeg
            audio = PyAudioSeg.from_file(str(out_path))
            seg_durations.append(len(audio) / 1000.0)
        except Exception:
            seg_durations.append(out_path.stat().st_size / 16000.0)

    # Stitch all segments into one WAV with 0.8s silence between
    logger.info("tts_stitching", segments=len(seg_paths))
    concat_audio_files_with_silence(
        audio_paths=seg_paths,
        output_path=full_audio,
        silence_sec=0.8,
    )

    total_duration = sum(seg_durations) + 0.8 * (len(seg_durations) - 1)

    logger.info(
        "tts_done",
        segments=len(seg_paths),
        total_duration=round(total_duration, 1),
        total_chars=total_chars,
    )

    return TTSResult(
        segment_audio_paths=seg_paths,
        full_audio_path=full_audio,
        total_duration_seconds=total_duration,
        total_chars=total_chars,
        per_segment_durations=seg_durations,
    )


def _load_cached(script: Script, run_id: str, output_root: Path, full_audio: Path) -> TTSResult:
    seg_paths = []
    seg_durations = []
    total_chars = 0

    for i, seg in enumerate(script.segments):
        p = segment_audio_path(output_root, run_id, i)
        seg_paths.append(p)
        total_chars += len(seg.narration)

        if p.exists():
            try:
                from pydub import AudioSegment as PyAudioSeg
                a = PyAudioSeg.from_file(str(p))
                seg_durations.append(len(a) / 1000.0)
            except Exception:
                seg_durations.append(p.stat().st_size / 16000.0)
        else:
            seg_durations.append(0.0)

    try:
        from pydub import AudioSegment as PyAudioSeg
        full = PyAudioSeg.from_file(str(full_audio))
        total_duration = len(full) / 1000.0
    except Exception:
        total_duration = sum(seg_durations)

    return TTSResult(
        segment_audio_paths=seg_paths,
        full_audio_path=full_audio,
        total_duration_seconds=total_duration,
        total_chars=total_chars,
        per_segment_durations=seg_durations,
    )
