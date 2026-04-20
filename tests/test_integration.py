"""Integration test: full dry-run pipeline with mocked external APIs."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chill_agent.config import Settings
from chill_agent.db.repo import Repository
from chill_agent.media.alignment import AlignmentResult, SegmentTimestamp
from chill_agent.orchestrator import make_one_video
from chill_agent.services.image.base import ImageResult
from chill_agent.services.llm.base import LLMResult
from chill_agent.services.tts.base import AudioResult


def _make_script_json() -> str:
    segments = []
    for i in range(7, 0, -1):
        segments.append({
            "number": i,
            "label": f"Weird Thing {i}",
            "narration": f"Number {i}: Weird Thing {i}\n\n" + ("This is sample narration. " * 40),
            "image_prompt": f"A cartoon illustrating weird thing {i}.",
        })

    return json.dumps({
        "title": "7 Creepy Things Your Brain Does",
        "description": "Your brain is doing wild stuff right now. {CHAPTERS} #psychology",
        "tags": ["psychology", "brain", "science", "weird", "creepy", "biology",
                 "education", "mindblowing", "facts", "youtube", "viral", "dark"],
        "thumbnail_prompt": "A cartoon brain with shocked expression, flat illustration.",
        "segments": segments,
        "outro": "That's all for today, I'll be making similar videos in the future. Subscribe to see them.",
    })


def _make_ideation_json() -> str:
    return json.dumps([
        {"title": "7 Creepy Things Your Brain Does", "brief": "Your brain is lying to you every day."}
    ])


@pytest.fixture
def settings(tmp_path):
    s = Settings(
        deepseek_api_key="fake-key",
        fish_audio_api_key="fake-tts-key",
        replicate_api_token="fake-replicate-key",
        tts_voice_id="fake-voice-id",
        output_dir=tmp_path / "outputs",
        db_url=f"sqlite:///{tmp_path}/test.db",
        enable_captions=False,  # Skip captions in test
    )
    s.output_dir.mkdir(parents=True, exist_ok=True)
    return s


@pytest.fixture
def repo(settings):
    r = Repository(settings.db_url)
    r.create_tables()
    return r


@pytest.fixture
def mock_llm():
    llm = MagicMock()

    def complete(*, system, user, temperature=1.0, json_mode=False, max_tokens=8192):
        if "Generate 10 viral" in user or "ideation" in system.lower():
            content = _make_ideation_json()
        else:
            content = _make_script_json()
        return LLMResult(content=content, input_tokens=100, output_tokens=200, model="deepseek-chat")

    llm.complete.side_effect = complete
    return llm


@pytest.fixture
def mock_tts(tmp_path):
    tts = MagicMock()

    def synthesize(text, voice_id, output_path):
        # Create a minimal WAV file (44 bytes header + silence)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_minimal_wav(output_path)
        return AudioResult(path=output_path, duration_seconds=10.0, sample_rate=44100, chars_synthesized=len(text))

    tts.synthesize.side_effect = synthesize
    return tts


@pytest.fixture
def mock_image_provider(tmp_path):
    provider = MagicMock()

    def generate(prompt, output_path, size=(1920, 1080)):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _write_minimal_png(output_path, size)
        return ImageResult(path=output_path, width=size[0], height=size[1], prompt_used=prompt)

    provider.generate.side_effect = generate
    return provider


def _write_minimal_wav(path: Path) -> None:
    """Write a minimal valid WAV file with 1 second of silence."""
    import struct
    import wave

    with wave.open(str(path), 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b'\x00' * 44100 * 2)  # 1 second silence


def _write_minimal_png(path: Path, size=(100, 100)) -> None:
    """Write a minimal valid PNG file."""
    try:
        from PIL import Image
        img = Image.new("RGB", size, color=(100, 150, 200))
        img.save(str(path), "PNG")
    except ImportError:
        # Fallback: write a 1x1 PNG header
        import base64
        # Minimal 1x1 red PNG
        minimal_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
        )
        path.write_bytes(minimal_png)


@pytest.mark.integration
def test_dry_run_full_pipeline(settings, repo, mock_llm, mock_tts, mock_image_provider, tmp_path):
    """Full pipeline dry-run with all external APIs mocked."""

    fake_alignment = AlignmentResult(
        segments=[
            SegmentTimestamp(
                segment_idx=i + 1,
                label=f"Weird Thing {7-i}",
                start_sec=float(i * 30),
                end_sec=float((i + 1) * 30),
            )
            for i in range(7)
        ],
        word_timestamps=[],
        srt_content=None,
        total_duration=210.0,
    )

    def mock_ffmpeg_run(args, **kwargs):
        """Simulate ffmpeg: succeed and create output file if -i present."""
        r = MagicMock()
        r.returncode = 0
        r.stdout = json.dumps({
            "format": {"duration": "300.0"},
            "streams": [{"codec_type": "audio"}],
        })
        r.stderr = ""
        # Create the output file so downstream stages can find it
        for i, arg in enumerate(args):
            if arg not in ("-y", "-f", "-i", "-vf", "-c", "-c:v", "-c:a",
                           "-t", "-map", "-r", "-an", "-b:a", "-shortest",
                           "-filter_complex", "-loop", "-stream_loop",
                           "-safe", "-select_streams", "-print_format",
                           "-show_format", "-show_streams", "-v"):
                if arg.endswith((".mp4", ".wav", ".mp3")) and not arg.startswith("-"):
                    # Check it's an output (not -i input)
                    prev = args[i - 1] if i > 0 else ""
                    if prev != "-i":
                        p = Path(arg)
                        p.parent.mkdir(parents=True, exist_ok=True)
                        if not p.exists():
                            _write_minimal_wav(p) if p.suffix == ".wav" else p.touch()
        return r

    with (
        patch("subprocess.run", side_effect=mock_ffmpeg_run),
        # Patch align at the orchestrator's import location
        patch("chill_agent.orchestrator.align", return_value=fake_alignment),
    ):
        result = make_one_video(
            settings=settings,
            repo=repo,
            llm=mock_llm,
            tts=mock_tts,
            image_provider=mock_image_provider,
            youtube=None,
            dry_run=True,
        )

    assert result.dry_run is True
    assert result.title == "7 Creepy Things Your Brain Does"
    assert result.youtube_video_id is None
    assert result.run_id

    # Verify DB was updated
    run = repo.get_run(result.run_id)
    assert run.status == "completed"
