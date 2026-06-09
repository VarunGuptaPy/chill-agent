"""Stage 3: TTS — synthesize narration per segment, stitch with silence.

Outro is synthesized as a fixed-text clip cached in assets/.
Intro is a silent visual beat (Gemini-generated image); no TTS for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.media.ffmpeg_ops import concat_audio_files_with_silence
from chill_agent.media.stick_figure import INTRO_TEXT, OUTRO_TEXT

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
    intro_duration: float = 0.0
    outro_duration: float = 0.0
    intro_audio_path: Optional[Path] = None
    outro_audio_path: Optional[Path] = None


def _audio_duration(path: Path) -> float:
    try:
        from pydub import AudioSegment as PyAudioSeg
        audio = PyAudioSeg.from_file(str(path))
        return len(audio) / 1000.0
    except Exception:
        return path.stat().st_size / 16000.0


def _ensure_fixed_audio(
    tts: TTSProvider,
    voice_id: str,
    assets_dir: Path,
    text: str,
    label: str,
    force: bool = False,
) -> tuple[Path, float]:
    """Synthesize a fixed TTS clip (intro or outro) into assets/ and cache it.

    Named with voice_id prefix so swapping voices regenerates automatically.
    """
    safe_vid = "".join(c if c.isalnum() else "_" for c in (voice_id or "default"))[:32]
    out_path = assets_dir / f"{label}_{safe_vid}.wav"

    assets_dir.mkdir(parents=True, exist_ok=True)

    if not out_path.exists() or force:
        logger.info(f"tts_synthesizing_{label}")
        tts.synthesize(text=text, voice_id=voice_id, output_path=out_path)
    else:
        logger.info(f"tts_{label}_cache_hit", path=str(out_path))

    return out_path, _audio_duration(out_path)


def synthesize_voice(
    tts: TTSProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    voice_id: str,
    force: bool = False,
) -> TTSResult:
    """Synthesize narration for each segment and stitch into a single WAV.

    Full audio layout: [intro] [seg0] [seg1] ... [segN] [outro]
    with 0.8s silence between each piece.
    """
    full_audio = full_audio_path(output_root, run_id)

    # Idempotency: if full audio already exists, load and return cached result
    if full_audio.exists() and not force:
        logger.info("tts_cache_hit", full_audio=str(full_audio))
        return _load_cached(tts, script, run_id, output_root, full_audio, voice_id)

    assets_dir = output_root.parent / "assets" / "audio"
    intro_path, intro_dur = _ensure_fixed_audio(tts, voice_id, assets_dir, INTRO_TEXT, "intro", force=False)
    outro_path, outro_dur = _ensure_fixed_audio(tts, voice_id, assets_dir, OUTRO_TEXT, "outro", force=False)

    # Per-segment synthesis
    seg_paths: List[Path] = []
    seg_durations: List[float] = []
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
        seg_durations.append(_audio_duration(out_path))

    # Stitch: intro + all segments + outro with 0.8s silence between
    logger.info("tts_stitching", segments=len(seg_paths))
    all_parts = [intro_path] + seg_paths + [outro_path]
    concat_audio_files_with_silence(
        audio_paths=all_parts,
        output_path=full_audio,
        silence_sec=0.8,
    )

    silence_gaps = len(all_parts) - 1
    total_duration = intro_dur + sum(seg_durations) + outro_dur + 0.8 * silence_gaps

    logger.info(
        "tts_done",
        segments=len(seg_paths),
        intro_duration=round(intro_dur, 1),
        outro_duration=round(outro_dur, 1),
        total_duration=round(total_duration, 1),
        total_chars=total_chars,
    )

    return TTSResult(
        segment_audio_paths=seg_paths,
        full_audio_path=full_audio,
        total_duration_seconds=total_duration,
        total_chars=total_chars,
        per_segment_durations=seg_durations,
        intro_duration=intro_dur,
        outro_duration=outro_dur,
        intro_audio_path=intro_path,
        outro_audio_path=outro_path,
    )


def _load_cached(
    tts: TTSProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    full_audio: Path,
    voice_id: str,
) -> TTSResult:
    seg_paths: List[Path] = []
    seg_durations: List[float] = []
    total_chars = 0

    for i, seg in enumerate(script.segments):
        p = segment_audio_path(output_root, run_id, i)
        seg_paths.append(p)
        total_chars += len(seg.narration)
        seg_durations.append(_audio_duration(p) if p.exists() else 0.0)

    try:
        from pydub import AudioSegment as PyAudioSeg
        full = PyAudioSeg.from_file(str(full_audio))
        total_duration = len(full) / 1000.0
    except Exception:
        total_duration = sum(seg_durations)

    assets_dir = output_root.parent / "assets" / "audio"
    safe_vid = "".join(c if c.isalnum() else "_" for c in (voice_id or "default"))[:32]
    intro_path = assets_dir / f"intro_{safe_vid}.wav"
    outro_path = assets_dir / f"outro_{safe_vid}.wav"
    intro_dur = _audio_duration(intro_path) if intro_path.exists() else 2.0
    outro_dur = _audio_duration(outro_path) if outro_path.exists() else 4.0

    return TTSResult(
        segment_audio_paths=seg_paths,
        full_audio_path=full_audio,
        total_duration_seconds=total_duration,
        total_chars=total_chars,
        per_segment_durations=seg_durations,
        intro_duration=intro_dur,
        outro_duration=outro_dur,
        intro_audio_path=intro_path if intro_path.exists() else None,
        outro_audio_path=outro_path if outro_path.exists() else None,
    )
