"""Tests for metadata finalization and chapter timestamp generation."""

import pytest
from pathlib import Path

from chill_agent.media.alignment import AlignmentResult, SegmentTimestamp
from chill_agent.stages.metadata import VideoMetadata, _build_chapters, finalize_metadata
from chill_agent.stages.script import Script, ScriptSegment
from chill_agent.stages.tts import TTSResult


def _make_tts_result() -> TTSResult:
    return TTSResult(
        segment_audio_paths=[],
        full_audio_path=Path("/tmp/full.wav"),
        total_duration_seconds=210.0,
        total_chars=1000,
        per_segment_durations=[30.0] * 7,
        intro_duration=2.0,
        outro_duration=4.0,
    )


def _make_script(title="7 Weird Brain Tricks") -> Script:
    segments = [
        ScriptSegment(
            number=i,
            label=f"Label {i}",
            narration=f"Number {i}: Label {i}\n\nContent " * 20,
            image_prompts=[f"Prompt {i}"],
        )
        for i in range(7, 0, -1)
    ]
    return Script(
        title=title,
        description="Intro text here. {CHAPTERS} #psychology #brain",
        tags=["psychology", "brain"],
        thumbnail_prompt="Brain cartoon",
        segments=segments,
        outro="That's all for today, I'll be making similar videos in the future. Subscribe to see them.",
    )


def _make_alignment() -> AlignmentResult:
    segments = [
        SegmentTimestamp(segment_idx=i, label=f"Label {i}", start_sec=float(i * 30), end_sec=float((i+1) * 30))
        for i in range(1, 8)
    ]
    return AlignmentResult(
        segments=segments,
        word_timestamps=[],
        srt_content=None,
        total_duration=210.0,
    )


def test_chapters_placeholder_replaced():
    script = _make_script()
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert "{CHAPTERS}" not in meta.description


def test_chapters_contain_timestamps():
    script = _make_script()
    chapters = _build_chapters(script, _make_tts_result())
    assert "0:00 Intro" in chapters
    assert "Number 1:" in chapters


def test_chapter_timestamps_formatted():
    from chill_agent.stages.tts import TTSResult
    script = _make_script()
    tts = TTSResult(
        segment_audio_paths=[],
        full_audio_path=Path("/tmp/full.wav"),
        total_duration_seconds=90.0,
        total_chars=100,
        per_segment_durations=[62.0] + [0.0] * 6,
        intro_duration=2.0,
        outro_duration=4.0,
    )
    chapters = _build_chapters(script, tts)
    assert "1:02" in chapters


def test_description_has_boilerplate():
    script = _make_script()
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert "Subscribe" in meta.description


def test_title_truncated_to_100_chars():
    long_title = "A" * 150
    script = _make_script(title=long_title)
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert len(meta.title) <= 100


def test_contains_synthetic_media_always_true():
    script = _make_script()
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert meta.contains_synthetic_media is True


def test_made_for_kids_always_false():
    script = _make_script()
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert meta.made_for_kids is False


def test_tags_limited_to_15():
    script = _make_script()
    script.tags = [f"tag{i}" for i in range(30)]
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert len(meta.tags) <= 15


def test_description_within_youtube_limit():
    script = _make_script()
    script.description = "A" * 4900 + " {CHAPTERS} #tag"
    alignment = _make_alignment()
    meta = finalize_metadata(script, alignment, _make_tts_result())
    assert len(meta.description) <= 5000
