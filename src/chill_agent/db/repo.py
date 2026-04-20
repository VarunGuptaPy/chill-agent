"""Database repository — all DB access goes through here."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator, List, Optional

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from chill_agent.db.models import Base, Metric, Run, Topic, Video


class Repository:
    def __init__(self, db_url: str) -> None:
        connect_args = {}
        if db_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        self._engine = create_engine(db_url, connect_args=connect_args)
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)

    def create_tables(self) -> None:
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        s = self._Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # ── Runs ──────────────────────────────────────────────────────────────────

    def start_run(self) -> Run:
        with self.session() as s:
            run = Run(status="running", current_stage="init")
            s.add(run)
            s.flush()
            return run

    def update_run_stage(self, run_id: str, stage: str) -> None:
        with self.session() as s:
            s.execute(
                update(Run).where(Run.id == run_id).values(current_stage=stage)
            )

    def finish_run(
        self,
        run_id: str,
        *,
        llm_input_tokens: int = 0,
        llm_output_tokens: int = 0,
        tts_chars: int = 0,
        image_count: int = 0,
        estimated_cost_usd: float = 0.0,
    ) -> None:
        with self.session() as s:
            s.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status="completed",
                    finished_at=datetime.now(timezone.utc),
                    llm_input_tokens=llm_input_tokens,
                    llm_output_tokens=llm_output_tokens,
                    tts_chars=tts_chars,
                    image_count=image_count,
                    estimated_cost_usd=estimated_cost_usd,
                )
            )

    def fail_run(self, run_id: str, error: str) -> None:
        with self.session() as s:
            s.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status="failed",
                    finished_at=datetime.now(timezone.utc),
                    error=str(error)[:2000],
                )
            )

    def get_run(self, run_id: str) -> Optional[Run]:
        with self.session() as s:
            return s.get(Run, run_id)

    # ── Topics ────────────────────────────────────────────────────────────────

    def add_topic(self, title: str, brief: str, embedding: Optional[list] = None) -> Topic:
        with self.session() as s:
            existing = s.execute(select(Topic).where(Topic.title == title)).scalar_one_or_none()
            if existing:
                return existing
            topic = Topic(
                title=title,
                brief=brief,
                embedding=json.dumps(embedding) if embedding else None,
            )
            s.add(topic)
            s.flush()
            return topic

    def recent_topics(self, limit: int = 200) -> List[Topic]:
        with self.session() as s:
            result = s.execute(
                select(Topic).order_by(Topic.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

    def topic_stats(self) -> List[dict]:
        """Return per-topic cluster performance scores for ideation weighting."""
        with self.session() as s:
            result = s.execute(
                select(
                    Video.title,
                    Metric.views_per_hour,
                )
                .join(Metric, Metric.video_id == Video.id)
                .where(Metric.views_per_hour.is_not(None))
                .order_by(Metric.recorded_at.desc())
                .limit(100)
            )
            return [{"title": row[0], "views_per_hour": row[1]} for row in result]

    # ── Videos ────────────────────────────────────────────────────────────────

    def add_video(
        self,
        run_id: str,
        title: str,
        topic_id: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None,
        video_path: Optional[str] = None,
        thumbnail_a_path: Optional[str] = None,
        thumbnail_b_path: Optional[str] = None,
    ) -> Video:
        with self.session() as s:
            video = Video(
                run_id=run_id,
                topic_id=topic_id,
                title=title,
                description=description,
                tags=json.dumps(tags) if tags else None,
                video_path=video_path,
                thumbnail_a_path=thumbnail_a_path,
                thumbnail_b_path=thumbnail_b_path,
            )
            s.add(video)
            s.flush()
            return video

    def mark_uploaded(
        self,
        video_id: str,
        youtube_video_id: str,
        scheduled_publish_at: datetime,
    ) -> None:
        with self.session() as s:
            s.execute(
                update(Video)
                .where(Video.id == video_id)
                .values(
                    youtube_video_id=youtube_video_id,
                    scheduled_publish_at=scheduled_publish_at,
                    uploaded_at=datetime.now(timezone.utc),
                )
            )

    def scheduled_publish_times(self) -> List[datetime]:
        """Return all future scheduled publish times (for slot-picking)."""
        now = datetime.now(timezone.utc)
        with self.session() as s:
            result = s.execute(
                select(Video.scheduled_publish_at)
                .where(Video.scheduled_publish_at.is_not(None))
            )
            times = []
            for row in result:
                t = row[0]
                if t is None:
                    continue
                # SQLite returns timezone-naive datetimes — normalize to UTC
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                if t > now:
                    times.append(t)
            return times

    def get_video(self, video_id: str) -> Optional[Video]:
        with self.session() as s:
            return s.get(Video, video_id)

    def recent_videos(self, limit: int = 30) -> List[Video]:
        with self.session() as s:
            result = s.execute(
                select(Video).order_by(Video.created_at.desc()).limit(limit)
            )
            return list(result.scalars().all())

    # ── Metrics ───────────────────────────────────────────────────────────────

    def upsert_metric(
        self,
        video_id: str,
        *,
        views: int = 0,
        likes: int = 0,
        comments: int = 0,
        ctr: Optional[float] = None,
        avd_seconds: Optional[float] = None,
        views_per_hour: Optional[float] = None,
    ) -> None:
        with self.session() as s:
            metric = Metric(
                video_id=video_id,
                views=views,
                likes=likes,
                comments=comments,
                ctr=ctr,
                avd_seconds=avd_seconds,
                views_per_hour=views_per_hour,
            )
            s.add(metric)

    def stats_summary(self) -> dict:
        """Return a summary dict for the stats CLI command."""
        with self.session() as s:
            total_videos = s.execute(select(Video)).scalars().all()
            uploaded = [v for v in total_videos if v.youtube_video_id]
            runs = s.execute(select(Run)).scalars().all()
            failed_runs = [r for r in runs if r.status == "failed"]
            total_cost = sum(r.estimated_cost_usd for r in runs)

            return {
                "total_videos": len(total_videos),
                "uploaded": len(uploaded),
                "total_runs": len(runs),
                "failed_runs": len(failed_runs),
                "total_cost_usd": round(total_cost, 4),
            }
