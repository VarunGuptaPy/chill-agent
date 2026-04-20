"""Stage 8: Metadata finalization — replace chapter placeholder, add boilerplate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import structlog

from chill_agent.media.alignment import AlignmentResult
from chill_agent.stages.script import Script

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


def finalize_metadata(script: Script, alignment: AlignmentResult) -> VideoMetadata:
    """Build final metadata: insert chapter timestamps, add boilerplate."""

    chapters = _build_chapters(alignment)
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


def _build_chapters(alignment: AlignmentResult) -> str:
    """Format chapter timestamps for YouTube description."""
    lines = ["0:00 Intro"]

    for seg in sorted(alignment.segments, key=lambda s: s.start_sec):
        t = seg.start_sec
        m = int(t // 60)
        s = int(t % 60)
        timestamp = f"{m}:{s:02d}"
        label = f"Number {seg.segment_idx}: {seg.label}"
        lines.append(f"{timestamp} {label}")

    return "\n".join(lines)
