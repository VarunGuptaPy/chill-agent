"""CLI entry point — chill-agent commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import structlog
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="chill-agent",
    help="Autonomous YouTube channel pipeline — Chill Dude Explains",
    no_args_is_help=True,
)
console = Console()
logger = structlog.get_logger()


def _get_deps(require_youtube: bool = False):
    """Shared setup: logging, settings, DB, providers."""
    from chill_agent.config import get_settings
    from chill_agent.db.repo import Repository
    from chill_agent.logging_setup import configure_logging
    from chill_agent.providers import build_image_provider, build_llm, build_tts, build_youtube

    configure_logging()
    settings = get_settings()
    repo = Repository(settings.db_url)
    repo.create_tables()

    llm = build_llm(settings)
    tts = build_tts(settings)
    image_provider = build_image_provider(settings)
    youtube = build_youtube(settings) if require_youtube else None

    return settings, repo, llm, tts, image_provider, youtube


@app.command()
def init():
    """Create the database, verify environment, and run YouTube OAuth flow."""
    from chill_agent.config import get_settings
    from chill_agent.db.repo import Repository
    from chill_agent.logging_setup import configure_logging

    configure_logging()
    settings = get_settings()
    repo = Repository(settings.db_url)
    repo.create_tables()
    console.print("[green]✓ Database initialized[/green]")

    # Check required env vars
    checks = [
        ("DEEPSEEK_API_KEY", settings.deepseek_api_key, True),
        ("FISH_AUDIO_API_KEY / ELEVENLABS_API_KEY", settings.fish_audio_api_key or settings.elevenlabs_api_key, True),
        ("POLLINATIONS_API_KEY", settings.pollinations_api_key, False),  # optional — anonymous works, just slower
        ("VERTEX_AI_KEY_FILE", Path(settings.vertex_ai_key_file).exists(), settings.image_provider == "gemini"),
        ("REPLICATE_API_TOKEN", settings.replicate_api_token, settings.image_provider == "replicate_flux"),
        ("TTS_VOICE_ID", settings.tts_voice_id, False),
        ("YOUTUBE_CLIENT_SECRETS_FILE", settings.youtube_client_secrets_file.exists(), False),
    ]

    all_good = True
    for name, value, required in checks:
        if value:
            console.print(f"[green]✓[/green] {name}")
        elif required:
            console.print(f"[red]✗ {name} is not set (REQUIRED)[/red]")
            all_good = False
        else:
            console.print(f"[yellow]⚠ {name} is not set (optional)[/yellow]")

    # Download Anton font if missing
    _ensure_font()

    # YouTube OAuth flow
    if settings.youtube_client_secrets_file.exists() and not settings.youtube_token_file.exists():
        console.print("\n[bold]Starting YouTube OAuth flow...[/bold]")
        try:
            from chill_agent.services.youtube.client import YouTubeClient
            yt = YouTubeClient(
                client_secrets_file=settings.youtube_client_secrets_file,
                token_file=settings.youtube_token_file,
            )
            yt._get_credentials()
            console.print("[green]✓ YouTube OAuth completed[/green]")
        except Exception as e:
            console.print(f"[red]YouTube OAuth failed: {e}[/red]")

    if all_good:
        console.print("\n[bold green]Setup complete. Run: chill-agent dry-run[/bold green]")
    else:
        console.print("\n[bold red]Fix the above issues before running the pipeline.[/bold red]")
        raise typer.Exit(1)


@app.command(name="run")
def run_scheduler(
    warmup: bool = typer.Option(False, "--warmup", help="Limit to 1 video/day for first 14 days"),
):
    """Start the scheduler and run forever (4 videos/day by default)."""
    settings, repo, llm, tts, image_provider, _ = _get_deps()
    if warmup:
        settings.warmup_mode = True

    from chill_agent.providers import build_youtube
    from chill_agent.scheduler import run_scheduler as _run_scheduler

    youtube = build_youtube(settings)
    _run_scheduler(settings, repo, llm, tts, image_provider, youtube)


@app.command(name="run-once")
def run_once(
    warmup: bool = typer.Option(False, "--warmup", help="Warmup mode"),
):
    """Produce and upload exactly one video, then exit."""
    settings, repo, llm, tts, image_provider, _ = _get_deps()
    if warmup:
        settings.warmup_mode = True

    from chill_agent.orchestrator import make_one_video
    from chill_agent.providers import build_youtube

    youtube = build_youtube(settings)
    result = make_one_video(
        settings=settings,
        repo=repo,
        llm=llm,
        tts=tts,
        image_provider=image_provider,
        youtube=youtube,
        dry_run=False,
    )
    console.print(f"\n[bold green]Done![/bold green] Title: {result.title}")
    console.print(f"YouTube ID: {result.youtube_video_id or 'not uploaded'}")
    console.print(f"Estimated cost: ${result.estimated_cost_usd:.4f}")


@app.command(name="dry-run")
def dry_run(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Resume a previous dry-run by run ID"),
    stage: Optional[str] = typer.Option(
        None, "--stage",
        help="Stage to resume from (ideation/script/tts/reprompt/images/alignment/assembly/thumbnail/metadata). "
             "Use 'reprompt' to regenerate image prompts from existing narration without redoing TTS. "
             "Auto-detected from cached files when --run-id is given.",
    ),
    mock_images: bool = typer.Option(False, "--mock-images", help="Use local placeholder images (free, for testing)"),
    force: bool = typer.Option(False, "--force", help="Force-rerun the specified stage(s) even if cached artifacts exist"),
):
    """Full pipeline without uploading to YouTube. Safe for testing.

    Resume example:    chill-agent dry-run --run-id <id> --stage images
    Auto-detect:       chill-agent dry-run --run-id <id>
    Force re-assemble: chill-agent dry-run --run-id <id> --stage alignment --force
    """
    settings, repo, llm, tts, image_provider, _ = _get_deps()

    if mock_images:
        from chill_agent.services.image.local_placeholder import LocalPlaceholderClient
        image_provider = LocalPlaceholderClient()
        console.print("[yellow]Using local placeholder images (--mock-images)[/yellow]")

    effective_stage: Optional[str] = stage

    if run_id and not stage:
        from chill_agent.orchestrator import detect_start_stage
        effective_stage = detect_start_stage(settings.output_dir, run_id)
        console.print(f"[cyan]Auto-detected resume point: [bold]{effective_stage}[/bold][/cyan]")
    elif run_id and stage:
        console.print(f"[cyan]Resuming from stage: [bold]{stage}[/bold][/cyan]")

    if force:
        console.print("[yellow]--force: cached artifacts for this stage will be regenerated[/yellow]")

    from chill_agent.orchestrator import make_one_video

    result = make_one_video(
        settings=settings,
        repo=repo,
        llm=llm,
        tts=tts,
        image_provider=image_provider,
        youtube=None,
        dry_run=True,
        force=force,
        resume_run_id=run_id,
        start_from_stage=effective_stage,
    )
    console.print(f"\n[bold green]Dry run complete![/bold green]")
    console.print(f"Title: {result.title}")
    console.print(f"Video: {result.video_path}")
    console.print(f"Estimated cost: ${result.estimated_cost_usd:.4f}")


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume (from DB)"),
    stage: Optional[str] = typer.Option(
        None, "--stage",
        help="Stage to resume from. Auto-detected from cached files if not specified.",
    ),
):
    """Resume a failed pipeline run from where it left off."""
    settings, repo, llm, tts, image_provider, _ = _get_deps()

    effective_stage: Optional[str] = stage
    if not stage:
        from chill_agent.orchestrator import detect_start_stage
        effective_stage = detect_start_stage(settings.output_dir, run_id)
        console.print(f"[cyan]Auto-detected resume point: [bold]{effective_stage}[/bold][/cyan]")
    else:
        console.print(f"[cyan]Resuming from stage: [bold]{stage}[/bold][/cyan]")

    from chill_agent.orchestrator import make_one_video
    from chill_agent.providers import build_youtube

    youtube = build_youtube(settings)
    result = make_one_video(
        settings=settings,
        repo=repo,
        llm=llm,
        tts=tts,
        image_provider=image_provider,
        youtube=youtube,
        dry_run=False,
        resume_run_id=run_id,
        start_from_stage=effective_stage,
    )
    console.print(f"[green]Resumed and completed: {result.title}[/green]")


@app.command()
def backfill(
    count: int = typer.Option(10, "-n", "--count", help="Number of videos to produce"),
    dry_run_flag: bool = typer.Option(False, "--dry-run", help="Skip uploading"),
):
    """Produce N videos quickly for channel warm-up."""
    settings, repo, llm, tts, image_provider, _ = _get_deps()

    from chill_agent.orchestrator import make_one_video
    from chill_agent.providers import build_youtube

    youtube = build_youtube(settings) if not dry_run_flag else None

    console.print(f"[bold]Backfilling {count} videos...[/bold]")
    for i in range(count):
        console.print(f"\n[blue]Video {i+1}/{count}[/blue]")
        try:
            result = make_one_video(
                settings=settings,
                repo=repo,
                llm=llm,
                tts=tts,
                image_provider=image_provider,
                youtube=youtube,
                dry_run=dry_run_flag,
            )
            console.print(f"[green]✓ {result.title}[/green]")
        except Exception as e:
            console.print(f"[red]✗ Failed: {e}[/red]")

    console.print(f"\n[bold green]Backfill complete.[/bold green]")


@app.command()
def stats():
    """Print performance summary from the database."""
    from chill_agent.config import get_settings
    from chill_agent.db.repo import Repository
    from chill_agent.logging_setup import configure_logging

    configure_logging()
    settings = get_settings()
    repo = Repository(settings.db_url)
    repo.create_tables()

    summary = repo.stats_summary()

    table = Table(title="chill-agent Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total videos produced", str(summary["total_videos"]))
    table.add_row("Videos uploaded to YouTube", str(summary["uploaded"]))
    table.add_row("Total pipeline runs", str(summary["total_runs"]))
    table.add_row("Failed runs", str(summary["failed_runs"]))
    table.add_row("Total estimated cost", f"${summary['total_cost_usd']:.4f}")

    console.print(table)

    # Recent videos
    videos = repo.recent_videos(10)
    if videos:
        vtable = Table(title="Recent Videos")
        vtable.add_column("Title", style="white")
        vtable.add_column("YouTube ID", style="cyan")
        vtable.add_column("Scheduled", style="yellow")

        for v in videos:
            vtable.add_row(
                v.title[:60],
                v.youtube_video_id or "-",
                v.scheduled_publish_at.strftime("%Y-%m-%d %H:%M UTC") if v.scheduled_publish_at else "-",
            )
        console.print(vtable)


@app.command()
def runs(
    limit: int = typer.Option(10, "-n", "--limit", help="Number of recent runs to show"),
):
    """List recent pipeline runs with their IDs and status."""
    from chill_agent.config import get_settings
    from chill_agent.db.models import Run
    from chill_agent.db.repo import Repository
    from chill_agent.logging_setup import configure_logging
    from sqlalchemy import select

    configure_logging()
    settings = get_settings()
    repo = Repository(settings.db_url)
    repo.create_tables()

    with repo.session() as s:
        result = s.execute(select(Run).order_by(Run.started_at.desc()).limit(limit))
        recent_runs = list(result.scalars().all())

    table = Table(title=f"Recent Runs (last {limit})")
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Stage", style="yellow")
    table.add_column("Started", style="dim")
    table.add_column("Error", style="red")

    for r in recent_runs:
        status_color = {"completed": "green", "failed": "red", "running": "yellow"}.get(r.status, "white")
        table.add_row(
            r.id,
            f"[{status_color}]{r.status}[/{status_color}]",
            r.current_stage,
            r.started_at.strftime("%m-%d %H:%M") if r.started_at else "-",
            (r.error or "")[:60],
        )

    console.print(table)
    console.print("\n[dim]To resume a dry-run: chill-agent dry-run --run-id <Run ID>[/dim]")
    console.print("[dim]To resume an upload run: chill-agent resume <Run ID>[/dim]")


def _ensure_font() -> None:
    """Download Anton font if not present."""
    font_path = Path(__file__).parent.parent.parent / "assets" / "fonts" / "Anton-Regular.ttf"
    if font_path.exists():
        return

    console.print("[yellow]Downloading Anton font...[/yellow]")
    try:
        import urllib.request
        font_path.parent.mkdir(parents=True, exist_ok=True)
        # Anton-Regular.ttf from Google Fonts (open-source)
        url = "https://fonts.gstatic.com/s/anton/v25/1Ptgg87LROyAm3Kz-C8.woff2"
        # Fallback to a simple TTF approach — use requests if available
        urllib.request.urlretrieve(
            "https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf",
            str(font_path),
        )
        console.print("[green]✓ Anton font downloaded[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not download font: {e}. Thumbnail will use system font.[/yellow]")


if __name__ == "__main__":
    app()
