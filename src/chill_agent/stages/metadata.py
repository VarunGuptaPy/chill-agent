"""Stage 8: Metadata finalization — replace chapter placeholder, add boilerplate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import structlog

from chill_agent.media.alignment import AlignmentResult
from chill_agent.stages.script import Script
from chill_agent.stages.tts import TTSResult

logger = structlog.get_logger()

_CHANNEL_BOILERPLATE = """
---
🔔 Subscribe for more mind-bending facts, weird science, and dark curiosity — new videos every week.

⚠️ This video uses AI-generated narration and illustrations.

#WeirdScience #Psychology #DarkCuriosity
"""


@dataclass
class VideoMetadata:
    title: str
    description: str
    tags: List[str]
    category_id: str = "27"  # Education
    language: str = "en"
    made_for_kids: bool = False
    contains_synthetic_media: bool = True  # ALWAYS TRUE


def finalize_metadata(script: Script, alignment: AlignmentResult, tts_result: TTSResult) -> VideoMetadata:
    """Build final metadata: insert chapter timestamps, add boilerplate."""

    chapters = _build_chapters(script, tts_result)
    description = script.description.replace("{CHAPTERS}", chapters)
    description = description + _CHANNEL_BOILERPLATE

    # Trim to YouTube's 5000 char limit
    if len(description) > 5000:
        description = description[:4990] + "..."

    # Trim title
    title = script.title[:100]

    # Trim tags
    tags = [t[:30] for t in script.tags[:15]]

    logger.info(
        "metadata_finalized",
        title=title,
        tags=len(tags),
        description_chars=len(description),
        chapters=chapters[:100],
    )

    return VideoMetadata(
        title=title,
        description=description,
        tags=tags,
    )


def _build_chapters(script: Script, tts_result: TTSResult) -> str:
    """Build chapter timestamps from TTS per-segment durations.

    TTS durations are exact (each segment synthesized individually), unlike
    alignment segment boundaries which can be wrong when number words appear
    in narration body text.
    """
    lines = ["0:00 Intro"]

    # Intro line "Let's get right into it." has no separate TTS segment;
    # segments start immediately at 0 in the full audio (before silence gap).
    # Accumulate: cursor starts at 0, each segment begins at cursor.
    silence_gap = 0.8
    cursor = 0.0

    for i, seg in enumerate(script.segments):
        m = int(cursor // 60)
        s = int(cursor % 60)
        timestamp = f"{m}:{s:02d}"
        lines.append(f"{timestamp} Number {seg.number}: {seg.label}")

        dur = tts_result.per_segment_durations[i] if i < len(tts_result.per_segment_durations) else 0.0
        cursor += dur + silence_gap

    return "\n".join(lines)
