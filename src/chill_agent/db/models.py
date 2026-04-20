"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Topic(Base):
    """A video topic/title — used for dedup and performance tracking."""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    brief: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    # Embedding for similarity filtering (stored as JSON array)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    videos: Mapped[list["Video"]] = relationship("Video", back_populates="topic")


class Run(Base):
    """A single pipeline execution run."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="running"
    )  # running | completed | failed
    current_stage: Mapped[str] = mapped_column(String(64), nullable=False, default="init")
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    output_dir: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Cost tracking
    llm_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    llm_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tts_chars: Mapped[int] = mapped_column(Integer, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    video: Mapped[Optional["Video"]] = relationship("Video", back_populates="run", uselist=False)


class Video(Base):
    """A completed video, ready to upload or already uploaded."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), nullable=False)
    topic_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("topics.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON array string

    # File paths
    video_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    thumbnail_a_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    thumbnail_b_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # YouTube
    youtube_video_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scheduled_publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    run: Mapped["Run"] = relationship("Run", back_populates="video")
    topic: Mapped[Optional["Topic"]] = relationship("Topic", back_populates="videos")
    metrics: Mapped[list["Metric"]] = relationship("Metric", back_populates="video")


class Metric(Base):
    """Performance metrics for a video — tracked over time."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Click-through rate %
    avd_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # Avg view duration
    views_per_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    video: Mapped["Video"] = relationship("Video", back_populates="metrics")
