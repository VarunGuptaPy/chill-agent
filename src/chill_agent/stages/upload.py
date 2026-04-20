"""Stage 9: YouTube upload — scheduled private video with AI disclosure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.db.repo import Repository
from chill_agent.media.ffmpeg_ops import validate_video
from chill_agent.services.youtube.client import YouTubeClient
from chill_agent.stages.metadata import VideoMetadata

logger = structlog.get_logger()


@dataclass
class UploadResult:
    youtube_video_id: str
    scheduled_publish_at: datetime
    quota_used: int


def upload_video(
    youtube: YouTubeClient,
    repo: Repository,
    video_path: Path,
    thumbnail_a_path: Path,
    metadata: VideoMetadata,
    publish_hours: List[int],
    dry_run: bool = False,
) -> UploadResult:
    """Validate, schedule, and upload video to YouTube."""

    # Safety validation before burning quota
    logger.info("upload_validating_video", path=str(video_path))
    validate_video(video_path)

    # Pick next available publish slot
    publish_at = _pick_publish_time(repo, publish_hours)

    if dry_run:
        logger.info(
            "upload_dry_run",
            title=metadata.title,
            publish_at=publish_at.isoformat(),
        )
        return UploadResult(
            youtube_video_id="DRY_RUN",
            scheduled_publish_at=publish_at,
            quota_used=0,
        )

    logger.info(
        "upload_start",
        title=metadata.title,
        publish_at=publish_at.isoformat(),
        file_mb=round(video_path.stat().st_size / 1024 / 1024, 1),
    )

    video_id = youtube.upload_video(
        video_path=video_path,
        title=metadata.title,
        description=metadata.description,
        tags=metadata.tags,
        publish_at=publish_at,
        category_id=metadata.category_id,
    )

    # Upload thumbnail
    if thumbnail_a_path.exists():
        youtube.set_thumbnail(video_id, thumbnail_a_path)
        quota_used = 1600 + 50
    else:
        quota_used = 1600

    logger.info(
        "upload_complete",
        video_id=video_id,
        quota_used=quota_used,
        publish_at=publish_at.isoformat(),
    )

    return UploadResult(
        youtube_video_id=video_id,
        scheduled_publish_at=publish_at,
        quota_used=quota_used,
    )


def _pick_publish_time(repo: Repository, publish_hours: List[int]) -> datetime:
    """Find the next available publish slot that isn't already taken."""
    now = datetime.now(timezone.utc)
    scheduled = set(repo.scheduled_publish_times())

    # Search up to 7 days out
    for day_offset in range(8):
        for hour in sorted(publish_hours):
            candidate = (now + timedelta(days=day_offset)).replace(
                hour=hour, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
            )
            if candidate <= now:
                continue
            # Check if this slot is taken (within ±30 min)
            taken = any(
                abs((candidate - s).total_seconds()) < 1800
                for s in scheduled
            )
            if not taken:
                return candidate

    # Fallback: 7 days from now at first hour
    return now + timedelta(days=7)
