"""WhisperX wrapper for word-level forced alignment.

Gracefully degrades to evenly-distributed timestamps if WhisperX is not available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import structlog

logger = structlog.get_logger()


@dataclass
class SegmentTimestamp:
    segment_idx: int
    label: str
    start_sec: float
    end_sec: float


@dataclass
class AlignmentResult:
    segments: List[SegmentTimestamp]
    word_timestamps: List[dict]  # raw word-level data
    srt_content: Optional[str]   # SRT captions if generated
    total_duration: float


def align(
    audio_path: Path,
    full_text: str,
    segment_labels: List[Tuple[int, str]],  # [(seg_idx, label_text_start), ...]
    output_srt_path: Optional[Path] = None,
) -> AlignmentResult:
    """Run forced alignment. Falls back to even distribution if WhisperX unavailable."""

    try:
        return _align_whisperx(audio_path, full_text, segment_labels, output_srt_path)
    except ImportError:
        logger.warning(
            "whisperx_not_available",
            message="WhisperX not installed. Using approximate timestamps. "
            "Install with: pip install whisperx",
        )
        return _align_approximate(audio_path, full_text, segment_labels, output_srt_path)


def _align_whisperx(
    audio_path: Path,
    full_text: str,
    segment_labels: List[Tuple[int, str]],
    output_srt_path: Optional[Path],
) -> AlignmentResult:
    import whisperx

    logger.info("whisperx_align_start", audio=str(audio_path))

    device = "cpu"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
    except ImportError:
        pass

    # Load + transcribe
    model = whisperx.load_model("base", device, compute_type="int8")
    audio = whisperx.load_audio(str(audio_path))
    result = model.transcribe(audio, batch_size=16)

    # Align
    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    aligned = whisperx.align(
        result["segments"], model_a, metadata, audio, device, return_char_alignments=False
    )

    word_timestamps = []
    for seg in aligned.get("segments", []):
        for w in seg.get("words", []):
            word_timestamps.append(
                {
                    "word": w.get("word", ""),
                    "start": w.get("start", 0),
                    "end": w.get("end", 0),
                }
            )

    total_duration = word_timestamps[-1]["end"] if word_timestamps else 0.0

    # Map segment labels to timestamps by finding their marker text in the word stream
    segment_times = _find_segment_boundaries(word_timestamps, segment_labels, total_duration)

    srt_content = None
    if output_srt_path:
        srt_content = _generate_srt(word_timestamps)
        output_srt_path.write_text(srt_content, encoding="utf-8")

    logger.info("whisperx_align_done", segments=len(segment_times), total_dur=total_duration)

    return AlignmentResult(
        segments=segment_times,
        word_timestamps=word_timestamps,
        srt_content=srt_content,
        total_duration=total_duration,
    )


def _align_approximate(
    audio_path: Path,
    full_text: str,
    segment_labels: List[Tuple[int, str]],
    output_srt_path: Optional[Path],
) -> AlignmentResult:
    """Distribute timestamps evenly by character count."""

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        total_duration = len(audio) / 1000.0
    except Exception:
        # If pydub fails, estimate from file size
        size = audio_path.stat().st_size
        total_duration = size / 16000.0

    total_chars = max(len(full_text), 1)

    # Find each segment's start character offset by searching for "Number X:" patterns.
    # Narration uses word numbers ("Number seven:"), not digits ("Number 7:").
    import re

    segment_offsets = []
    for idx, label_text in segment_labels:
        word_num = _num_to_word(idx)
        # Match both digit form ("Number 7:") and word form ("Number seven:")
        pattern = rf"Number\s+(?:{idx}|{word_num})\s*:"
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            segment_offsets.append((idx, match.start()))
        else:
            segment_offsets.append((idx, 0))

    segment_offsets.sort(key=lambda x: x[1])

    segment_times = []
    for i, (seg_idx, char_start) in enumerate(segment_offsets):
        start_sec = (char_start / total_chars) * total_duration
        if i + 1 < len(segment_offsets):
            char_end = segment_offsets[i + 1][1]
            end_sec = (char_end / total_chars) * total_duration
        else:
            end_sec = total_duration

        label = next((lbl for idx, lbl in segment_labels if idx == seg_idx), "")
        segment_times.append(
            SegmentTimestamp(
                segment_idx=seg_idx,
                label=label,
                start_sec=round(start_sec, 2),
                end_sec=round(end_sec, 2),
            )
        )

    return AlignmentResult(
        segments=segment_times,
        word_timestamps=[],
        srt_content=None,
        total_duration=total_duration,
    )


def _find_segment_boundaries(
    word_timestamps: List[dict],
    segment_labels: List[Tuple[int, str]],
    total_duration: float,
) -> List[SegmentTimestamp]:
    """Find the time when each 'Number X:' phrase starts in the word stream."""
    import re

    result = []
    words = [w["word"].lower().strip(".,!?") for w in word_timestamps]
    times = [w["start"] for w in word_timestamps]

    for seg_idx, label_hint in segment_labels:
        # Search for "number" followed by digit sequence
        found_start = None
        pattern_words = ["number"]
        for i, w in enumerate(words):
            if w in ("number",):
                # Check if next word(s) form the number
                next_words = words[i + 1 : i + 3]
                joined = " ".join(next_words)
                # Match numeric (e.g., "seven") or digit
                if str(seg_idx) in joined or _num_to_word(seg_idx) in joined:
                    found_start = times[i]
                    break

        if found_start is None:
            # Fallback: evenly distribute
            found_start = (seg_idx / max(len(segment_labels), 1)) * total_duration

        result.append(
            SegmentTimestamp(
                segment_idx=seg_idx,
                label=label_hint,
                start_sec=round(found_start, 2),
                end_sec=0.0,  # filled in below
            )
        )

    # Fill end times
    result.sort(key=lambda x: x.start_sec)
    for i, seg in enumerate(result):
        if i + 1 < len(result):
            seg.end_sec = result[i + 1].start_sec
        else:
            seg.end_sec = total_duration

    return result


_NUM_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}


def _num_to_word(n: int) -> str:
    return _NUM_WORDS.get(n, str(n))


def get_image_switch_times(
    segment_start: float,
    segment_end: float,
    num_images: int,
    word_timestamps: List[dict],
) -> List[float]:
    """Return switch timestamps for num_images images within a segment.

    Tries to cut at sentence boundaries; falls back to even splits.
    Returns a list of `num_images + 1` timestamps: [start, cut1, cut2, ..., end]
    """
    if num_images <= 1:
        return [segment_start, segment_end]

    # Find words inside this segment
    seg_words = [
        w for w in word_timestamps
        if segment_start <= w.get("start", 0) < segment_end
    ]

    # Sentence boundary = word ending with . ! ?
    sentence_ends = [
        w["end"]
        for w in seg_words
        if w.get("word", "").rstrip().endswith((".", "!", "?"))
    ]

    if len(sentence_ends) >= num_images - 1:
        # Pick evenly-spaced sentence boundaries as cut points
        step = max(1, len(sentence_ends) // num_images)
        cut_points = [sentence_ends[min(i * step, len(sentence_ends) - 1)] for i in range(1, num_images)]
    else:
        # Even splits
        duration = segment_end - segment_start
        cut_points = [
            segment_start + (duration * i / num_images)
            for i in range(1, num_images)
        ]

    return [segment_start] + cut_points + [segment_end]


def _generate_srt(word_timestamps: List[dict]) -> str:
    """Generate SRT caption file from word-level timestamps (phrase grouping)."""
    lines = []
    idx = 1
    i = 0
    words = word_timestamps

    while i < len(words):
        # Group 6-8 words per caption
        group = words[i : i + 7]
        if not group:
            break

        start = group[0].get("start", 0)
        end = group[-1].get("end", start + 1)
        text = " ".join(w.get("word", "") for w in group).strip()

        lines.append(str(idx))
        lines.append(f"{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}")
        lines.append(text)
        lines.append("")

        idx += 1
        i += 7

    return "\n".join(lines)


def _fmt_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
