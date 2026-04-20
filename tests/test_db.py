"""Tests for the database repository layer."""

import pytest
from datetime import datetime, timezone

from chill_agent.db.repo import Repository


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "test.db"
    r = Repository(f"sqlite:///{db_path}")
    r.create_tables()
    return r


def test_start_run(repo):
    run = repo.start_run()
    assert run.id
    assert run.status == "running"
    assert run.current_stage == "init"


def test_update_run_stage(repo):
    run = repo.start_run()
    repo.update_run_stage(run.id, "script")
    fetched = repo.get_run(run.id)
    assert fetched.current_stage == "script"


def test_finish_run(repo):
    run = repo.start_run()
    repo.finish_run(
        run.id,
        llm_input_tokens=1000,
        llm_output_tokens=2000,
        tts_chars=5000,
        image_count=8,
        estimated_cost_usd=0.19,
    )
    fetched = repo.get_run(run.id)
    assert fetched.status == "completed"
    assert fetched.llm_input_tokens == 1000
    assert fetched.estimated_cost_usd == pytest.approx(0.19)


def test_fail_run(repo):
    run = repo.start_run()
    repo.fail_run(run.id, "Something went wrong")
    fetched = repo.get_run(run.id)
    assert fetched.status == "failed"
    assert "Something went wrong" in fetched.error


def test_add_and_retrieve_topic(repo):
    topic = repo.add_topic("Creepy Brain Glitches", "Your brain does weird stuff at night.")
    assert topic.id
    assert topic.title == "Creepy Brain Glitches"

    topics = repo.recent_topics(10)
    assert any(t.title == "Creepy Brain Glitches" for t in topics)


def test_recent_topics_limit(repo):
    for i in range(5):
        repo.add_topic(f"Topic {i}", f"Brief {i}")
    topics = repo.recent_topics(3)
    assert len(topics) == 3


def test_add_video(repo):
    run = repo.start_run()
    video = repo.add_video(
        run_id=run.id,
        title="7 Weird Things Your Brain Does",
        tags=["psychology", "brain"],
    )
    assert video.id
    assert video.title == "7 Weird Things Your Brain Does"


def test_mark_uploaded(repo):
    run = repo.start_run()
    video = repo.add_video(run_id=run.id, title="Test Video")
    pub_at = datetime(2026, 5, 1, 8, 0, 0, tzinfo=timezone.utc)
    repo.mark_uploaded(video.id, "abc123", pub_at)

    fetched = repo.get_video(video.id)
    assert fetched.youtube_video_id == "abc123"


def test_scheduled_publish_times(repo):
    run = repo.start_run()
    video = repo.add_video(run_id=run.id, title="Test")
    pub_at = datetime(2026, 12, 1, 8, 0, 0, tzinfo=timezone.utc)
    repo.mark_uploaded(video.id, "yt123", pub_at)

    times = repo.scheduled_publish_times()
    assert any(t == pub_at for t in times)


def test_upsert_metric(repo):
    run = repo.start_run()
    video = repo.add_video(run_id=run.id, title="Test")
    repo.upsert_metric(video.id, views=1000, likes=50, views_per_hour=100.0)

    stats = repo.stats_summary()
    assert stats["total_videos"] == 1


def test_stats_summary(repo):
    summary = repo.stats_summary()
    assert "total_videos" in summary
    assert "uploaded" in summary
    assert "total_runs" in summary
    assert "failed_runs" in summary
    assert "total_cost_usd" in summary
