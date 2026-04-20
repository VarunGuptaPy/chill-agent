"""Orchestrator — runs the full pipeline for one video.

Each stage writes artifacts to disk. The pipeline is idempotent:
if a stage already completed (artifacts exist on disk), it's skipped unless --force.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

from chill_agent.config import Settings
from chill_agent.db.repo import Repository
from chill_agent.media.alignment import align
from chill_agent.services.image.base import ImageProvider
from chill_agent.services.llm.base import LLMProvider
from chill_agent.services.tts.base import TTSProvider
from chill_agent.services.youtube.client import YouTubeClient
from chill_agent.stages.assembly import assemble_video
from chill_agent.stages.ideation import ideate
from chill_agent.stages.images import generate_images
from chill_agent.stages.metadata import finalize_metadata
from chill_agent.stages.script import Script, generate_script
from chill_agent.stages.thumbnail import make_thumbnail
from chill_agent.stages.tts import synthesize_voice
from chill_agent.stages.upload import upload_video
from chill_agent.utils.alerts import send_alert
from chill_agent.utils.paths import (
    alignment_cache_path,
    run_dir,
    script_cache_path,
    srt_path,
)

logger = structlog.get_logger()


@dataclass
class PipelineResult:
    run_id: str
    youtube_video_id: Optional[str]
    video_path: Optional[Path]
    title: str
    dry_run: bool
    estimated_cost_usd: float


def make_one_video(
    settings: Settings,
    repo: Repository,
    llm: LLMProvider,
    tts: TTSProvider,
    image_provider: ImageProvider,
    youtube: Optional[YouTubeClient] = None,
    dry_run: bool = False,
    force: bool = False,
    resume_run_id: Optional[str] = None,
) -> PipelineResult:
    """Run the full pipeline for one video. Idempotent — safe to resume."""

    # Start or resume a run
    if resume_run_id:
        run = repo.get_run(resume_run_id)
        if not run:
            raise ValueError(f"Run {resume_run_id} not found in DB")
        run_id = resume_run_id
        logger.info("pipeline_resuming", run_id=run_id, last_stage=run.current_stage)
    else:
        run = repo.start_run()
        run_id = run.id
        logger.info("pipeline_start", run_id=run_id, dry_run=dry_run)

    output_root = settings.output_dir
    output_root.mkdir(parents=True, exist_ok=True)
    run_output = run_dir(output_root, run_id)

    # Cost tracking
    total_input_tokens = 0
    total_output_tokens = 0
    total_tts_chars = 0
    total_images = 0

    try:
        # ── Stage 1: Ideation ─────────────────────────────────────────────────
        repo.update_run_stage(run_id, "ideation")
        past_topics = repo.recent_topics(200)
        perf_stats = repo.topic_stats()
        ideation = ideate(llm=llm, past_topics=past_topics, performance_stats=perf_stats)
        total_input_tokens += ideation.llm_input_tokens
        total_output_tokens += ideation.llm_output_tokens

        # ── Stage 2: Script ───────────────────────────────────────────────────
        repo.update_run_stage(run_id, "script")
        script_cache = script_cache_path(output_root, run_id)

        if script_cache.exists() and not force:
            logger.info("script_cache_hit", run_id=run_id)
            script = _load_script_cache(script_cache)
        else:
            script = generate_script(llm=llm, title=ideation.title, brief=ideation.brief)
            _save_script_cache(script, script_cache)
            total_input_tokens += script.llm_input_tokens
            total_output_tokens += script.llm_output_tokens

        # Save topic to DB
        topic = repo.add_topic(title=script.title, brief=ideation.brief)

        # ── Stage 3: TTS ──────────────────────────────────────────────────────
        repo.update_run_stage(run_id, "tts")
        tts_result = synthesize_voice(
            tts=tts,
            script=script,
            run_id=run_id,
            output_root=output_root,
            voice_id=settings.tts_voice_id,
            force=force,
        )
        total_tts_chars += tts_result.total_chars

        # ── Stage 4: Images ───────────────────────────────────────────────────
        repo.update_run_stage(run_id, "images")
        images_result = generate_images(
            image_provider=image_provider,
            script=script,
            run_id=run_id,
            output_root=output_root,
            force=force,
        )
        total_images += images_result.total_images

        # ── Stage 5: Alignment ────────────────────────────────────────────────
        repo.update_run_stage(run_id, "alignment")
        alignment_cache = alignment_cache_path(output_root, run_id)
        srt_file = srt_path(output_root, run_id)

        if alignment_cache.exists() and not force:
            logger.info("alignment_cache_hit", run_id=run_id)
            alignment = _load_alignment_cache(alignment_cache)
        else:
            segment_labels = [(seg.number, seg.label) for seg in script.segments]
            alignment = align(
                audio_path=tts_result.full_audio_path,
                full_text=script.full_narration,
                segment_labels=segment_labels,
                output_srt_path=srt_file if settings.enable_captions else None,
            )
            _save_alignment_cache(alignment, alignment_cache)

        # ── Stage 6: Assembly ─────────────────────────────────────────────────
        repo.update_run_stage(run_id, "assembly")
        music_dir = Path(__file__).parent.parent.parent / "assets" / "music"
        final_video = assemble_video(
            run_id=run_id,
            output_root=output_root,
            tts_result=tts_result,
            segment_image_paths=images_result.segment_image_paths,
            alignment=alignment,
            music_dir=music_dir if music_dir.exists() else None,
            enable_captions=settings.enable_captions,
            force=force,
        )

        # ── Stage 7: Thumbnail ────────────────────────────────────────────────
        repo.update_run_stage(run_id, "thumbnail")
        thumb_a, thumb_b = make_thumbnail(
            raw_image_path=images_result.thumbnail_path,
            title=script.title,
            output_root=output_root,
            run_id=run_id,
            force=force,
        )

        # ── Stage 8: Metadata ─────────────────────────────────────────────────
        repo.update_run_stage(run_id, "metadata")
        metadata = finalize_metadata(script=script, alignment=alignment)

        # Save video record to DB
        video_record = repo.add_video(
            run_id=run_id,
            title=script.title,
            topic_id=topic.id,
            description=metadata.description,
            tags=metadata.tags,
            video_path=str(final_video),
            thumbnail_a_path=str(thumb_a),
            thumbnail_b_path=str(thumb_b),
        )

        # ── Stage 9: Upload ───────────────────────────────────────────────────
        youtube_video_id = None
        if not dry_run and youtube:
            repo.update_run_stage(run_id, "upload")
            upload_result = upload_video(
                youtube=youtube,
                repo=repo,
                video_path=final_video,
                thumbnail_a_path=thumb_a,
                metadata=metadata,
                publish_hours=settings.publish_hours_list,
                dry_run=False,
            )
            youtube_video_id = upload_result.youtube_video_id
            repo.mark_uploaded(
                video_id=video_record.id,
                youtube_video_id=youtube_video_id,
                scheduled_publish_at=upload_result.scheduled_publish_at,
            )
        elif dry_run:
            logger.info("pipeline_dry_run_skip_upload", title=script.title)

        # ── Cost tracking ──────────────────────────────────────────────────────
        cost = _estimate_cost(total_input_tokens, total_output_tokens, total_tts_chars, total_images)

        repo.finish_run(
            run_id=run_id,
            llm_input_tokens=total_input_tokens,
            llm_output_tokens=total_output_tokens,
            tts_chars=total_tts_chars,
            image_count=total_images,
            estimated_cost_usd=cost,
        )

        logger.info(
            "pipeline_complete",
            run_id=run_id,
            title=script.title,
            youtube_video_id=youtube_video_id or "NOT_UPLOADED",
            estimated_cost_usd=round(cost, 4),
            dry_run=dry_run,
        )

        return PipelineResult(
            run_id=run_id,
            youtube_video_id=youtube_video_id,
            video_path=final_video,
            title=script.title,
            dry_run=dry_run,
            estimated_cost_usd=cost,
        )

    except Exception as e:
        repo.fail_run(run_id=run_id, error=str(e))
        current_run = repo.get_run(run_id)
        stage = current_run.current_stage if current_run else "unknown"

        alert_msg = (
            f"🚨 chill-agent pipeline FAILED\n"
            f"run_id: {run_id}\n"
            f"stage: {stage}\n"
            f"error: {str(e)[:500]}"
        )
        send_alert(
            alert_msg,
            discord_url=settings.discord_webhook_url,
            slack_url=settings.slack_webhook_url,
        )

        logger.error(
            "pipeline_failed",
            run_id=run_id,
            stage=stage,
            error=str(e),
        )
        raise


def _estimate_cost(
    input_tokens: int,
    output_tokens: int,
    tts_chars: int,
    image_count: int,
) -> float:
    llm_cost = (input_tokens / 1_000_000 * 0.28) + (output_tokens / 1_000_000 * 0.42)
    tts_cost = tts_chars / 1_000_000 * 15.0  # Fish Audio ~$15/1M chars
    image_cost = image_count * 0.04  # Flux 1.1 Pro ~$0.04/image
    return llm_cost + tts_cost + image_cost


def _save_script_cache(script: Script, path: Path) -> None:
    import dataclasses
    data = {
        "title": script.title,
        "description": script.description,
        "tags": script.tags,
        "thumbnail_prompt": script.thumbnail_prompt,
        "segments": [
            {
                "number": s.number,
                "label": s.label,
                "narration": s.narration,
                "image_prompt": s.image_prompt,
            }
            for s in script.segments
        ],
        "outro": script.outro,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_script_cache(path: Path) -> Script:
    from chill_agent.stages.script import ScriptSegment
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [
        ScriptSegment(
            number=s["number"],
            label=s["label"],
            narration=s["narration"],
            image_prompt=s["image_prompt"],
        )
        for s in data.get("segments", [])
    ]
    return Script(
        title=data["title"],
        description=data.get("description", ""),
        tags=data.get("tags", []),
        thumbnail_prompt=data.get("thumbnail_prompt", ""),
        segments=segments,
        outro=data.get("outro", ""),
    )


def _save_alignment_cache(alignment, path: Path) -> None:
    data = {
        "segments": [
            {
                "segment_idx": s.segment_idx,
                "label": s.label,
                "start_sec": s.start_sec,
                "end_sec": s.end_sec,
            }
            for s in alignment.segments
        ],
        "total_duration": alignment.total_duration,
        "srt_content": alignment.srt_content,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_alignment_cache(path: Path):
    from chill_agent.media.alignment import AlignmentResult, SegmentTimestamp
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = [
        SegmentTimestamp(
            segment_idx=s["segment_idx"],
            label=s["label"],
            start_sec=s["start_sec"],
            end_sec=s["end_sec"],
        )
        for s in data.get("segments", [])
    ]
    return AlignmentResult(
        segments=segments,
        word_timestamps=[],
        srt_content=data.get("srt_content"),
        total_duration=data.get("total_duration", 0.0),
    )
