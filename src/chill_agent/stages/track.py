"""Stage 10: Performance tracking — polls YouTube Analytics every 6 hours."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

import structlog

from chill_agent.db.models import Video
from chill_agent.db.repo import Repository
from chill_agent.services.youtube.client import YouTubeClient

logger = structlog.get_logger()


def track_performance(
    youtube: YouTubeClient,
    repo: Repository,
    channel_id: str,
    lookback_days: int = 30,
) -> None:
    """Fetch and store performance stats for recent videos."""

    videos = repo.recent_videos(limit=50)
    uploaded = [v for v in videos if v.youtube_video_id and v.youtube_video_id != "DRY_RUN"]

    if not uploaded:
        logger.info("track_no_videos_to_track")
        return

    video_ids = [v.youtube_video_id for v in uploaded]

    logger.info("track_fetching_stats", video_count=len(video_ids))

    # Basic stats (views, likes, comments)
    try:
        stats_items = youtube.get_video_stats(video_ids)
        _process_basic_stats(repo, uploaded, stats_items)
    except Exception as e:
        logger.error("track_basic_stats_failed", error=str(e))

    # Analytics (CTR, AVD) — optional, may fail if channel is new
    if channel_id:
        try:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=lookback_days)
            ).strftime("%Y-%m-%d")

            analytics = youtube.get_analytics(
                channel_id=channel_id,
                video_ids=video_ids,
                start_date=start_date,
                end_date=end_date,
            )
            _process_analytics(repo, uploaded, analytics)
        except Exception as e:
            logger.warning("track_analytics_failed", error=str(e))

    logger.info("track_done", videos_tracked=len(uploaded))


def _process_basic_stats(
    repo: Repository,
    videos: List[Video],
    stats_items: List[dict],
) -> None:
    stats_map = {item["id"]: item.get("statistics", {}) for item in stats_items}

    for video in videos:
        stats = stats_map.get(video.youtube_video_id, {})
        if not stats:
            continue

        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        # Compute views/hour since publish
        hours_since_publish = None
        if video.scheduled_publish_at:
            now = datetime.now(timezone.utc)
            pub = video.scheduled_publish_at
            if pub.tzinfo is None:
                pub = pub.replace(tzinfo=timezone.utc)
            delta_hours = (now - pub).total_seconds() / 3600
            hours_since_publish = max(delta_hours, 0.1)

        vph = views / hours_since_publish if hours_since_publish else None

        repo.upsert_metric(
            video.id,
            views=views,
            likes=likes,
            comments=comments,
            views_per_hour=vph,
        )
        logger.debug("track_stats_stored", video_id=video.youtube_video_id, views=views)


def _process_analytics(
    repo: Repository,
    videos: List[Video],
    analytics: dict,
) -> None:
    rows = analytics.get("rows", [])
    col_headers = [h.get("name") for h in analytics.get("columnHeaders", [])]

    if not rows or "video" not in col_headers:
        return

    vid_idx = col_headers.index("video")
    views_idx = col_headers.index("views") if "views" in col_headers else None
    avd_idx = col_headers.index("averageViewDuration") if "averageViewDuration" in col_headers else None
    ctr_idx = col_headers.index("clickThroughRate") if "clickThroughRate" in col_headers else None

    video_map = {v.youtube_video_id: v for v in videos}

    for row in rows:
        yt_id = row[vid_idx]
        video = video_map.get(yt_id)
        if not video:
            continue

        avd = float(row[avd_idx]) if avd_idx is not None else None
        ctr = float(row[ctr_idx]) * 100 if ctr_idx is not None else None  # Convert to %

        repo.upsert_metric(
            video.id,
            avd_seconds=avd,
            ctr=ctr,
        )
