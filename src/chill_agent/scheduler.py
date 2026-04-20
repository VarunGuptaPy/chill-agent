"""APScheduler-based run loop — runs the pipeline on a cron schedule."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from chill_agent.config import Settings
from chill_agent.db.repo import Repository
from chill_agent.orchestrator import make_one_video
from chill_agent.services.image.base import ImageProvider
from chill_agent.services.llm.base import LLMProvider
from chill_agent.services.tts.base import TTSProvider
from chill_agent.services.youtube.client import YouTubeClient

logger = structlog.get_logger()


def run_scheduler(
    settings: Settings,
    repo: Repository,
    llm: LLMProvider,
    tts: TTSProvider,
    image_provider: ImageProvider,
    youtube: Optional[YouTubeClient] = None,
) -> None:
    """Start the APScheduler loop. Runs indefinitely until interrupted."""

    videos_per_day = settings.effective_videos_per_day
    # Interval in seconds between runs
    interval_seconds = int(86400 / max(videos_per_day, 1))

    logger.info(
        "scheduler_starting",
        videos_per_day=videos_per_day,
        interval_seconds=interval_seconds,
        warmup_mode=settings.warmup_mode,
    )

    scheduler = BackgroundScheduler()

    def _run_one():
        logger.info("scheduler_triggered", time=datetime.now(timezone.utc).isoformat())
        try:
            make_one_video(
                settings=settings,
                repo=repo,
                llm=llm,
                tts=tts,
                image_provider=image_provider,
                youtube=youtube,
                dry_run=False,
            )
        except Exception as e:
            logger.error("scheduler_pipeline_error", error=str(e))

    scheduler.add_job(
        _run_one,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="pipeline",
        next_run_time=datetime.now(timezone.utc),  # run immediately on start
    )
    scheduler.start()
    logger.info("scheduler_running", press_ctrl_c="to stop")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("scheduler_stopped")
