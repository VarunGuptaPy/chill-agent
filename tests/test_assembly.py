"""Tests for FFmpeg command building (no actual encoding)."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chill_agent.media.ffmpeg_ops import (
    _KEN_BURNS_MODES,
    _run_ffmpeg,
    build_ken_burns_clip,
    concat_video_clips,
    probe_duration,
)


class TestKenBurnsModes:
    def test_modes_count(self):
        assert len(_KEN_BURNS_MODES) == 4

    def test_mode_cycling(self):
        modes_used = set()
        for i in range(8):
            mode = _KEN_BURNS_MODES[i % len(_KEN_BURNS_MODES)]
            modes_used.add(mode)
        assert modes_used == {"zoom_in", "zoom_out", "pan_left", "pan_right"}


class TestRunFFmpeg:
    def test_raises_on_ffmpeg_failure(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Error: No such file or directory"
            mock_run.return_value = mock_result

            with pytest.raises(RuntimeError, match="FFmpeg failed"):
                _run_ffmpeg(["-i", "nonexistent.mp4", "out.mp4"])

    def test_succeeds_on_zero_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            _run_ffmpeg(["-version"])  # Should not raise


class TestBuildKenBurnsClip:
    def test_builds_command_with_correct_filters(self, tmp_path):
        img = tmp_path / "image.png"
        img.touch()
        out = tmp_path / "clip.mp4"

        captured_args = []

        def mock_run(args, **kwargs):
            captured_args.extend(args)
            result = MagicMock()
            result.returncode = 0
            return result

        with patch("subprocess.run", side_effect=mock_run):
            build_ken_burns_clip(
                image_path=img,
                output_path=out,
                duration=10.0,
                mode_idx=0,  # zoom_in
            )

        cmd_str = " ".join(captured_args)
        assert "zoompan" in cmd_str
        assert "libx264" in cmd_str
        assert "yuv420p" in cmd_str
        assert "1920x1080" in cmd_str

    def test_zoom_in_mode(self, tmp_path):
        img = tmp_path / "image.png"
        img.touch()
        out = tmp_path / "clip.mp4"
        captured = []

        def mock_run(args, **kwargs):
            captured.extend(args)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("subprocess.run", side_effect=mock_run):
            build_ken_burns_clip(img, out, 10.0, mode_idx=0)

        cmd = " ".join(captured)
        # zoom_in: z increases, centered
        assert "0.08" in cmd

    def test_different_modes_produce_different_commands(self, tmp_path):
        img = tmp_path / "image.png"
        img.touch()

        commands = {}
        for mode_idx in range(4):
            captured = []

            def mock_run(args, mode_idx=mode_idx, **kwargs):
                captured.extend(args)
                r = MagicMock()
                r.returncode = 0
                return r

            out = tmp_path / f"clip_{mode_idx}.mp4"
            with patch("subprocess.run", side_effect=mock_run):
                build_ken_burns_clip(img, out, 10.0, mode_idx=mode_idx)

            commands[mode_idx] = " ".join(captured)

        # All 4 modes should produce distinct filter strings
        unique_cmds = set(commands.values())
        assert len(unique_cmds) == 4


class TestConcatClips:
    def test_creates_concat_list_file(self, tmp_path):
        clips = [tmp_path / f"seg_{i}.mp4" for i in range(3)]
        for c in clips:
            c.touch()
        out = tmp_path / "concat.mp4"

        captured = []

        def mock_run(args, **kwargs):
            captured.extend(args)
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("subprocess.run", side_effect=mock_run):
            concat_video_clips(clips, out)

        cmd = " ".join(captured)
        assert "concat" in cmd
        assert "-f" in cmd


class TestProbeDuration:
    def test_parses_duration_from_ffprobe(self, tmp_path):
        dummy_video = tmp_path / "test.mp4"
        dummy_video.touch()

        import json

        ffprobe_output = json.dumps({
            "format": {"duration": "125.8"}
        })

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ffprobe_output

        with patch("subprocess.run", return_value=mock_result):
            duration = probe_duration(dummy_video)

        assert duration == pytest.approx(125.8)

    def test_raises_on_ffprobe_failure(self, tmp_path):
        dummy = tmp_path / "test.mp4"
        dummy.touch()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "No such file"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                probe_duration(dummy)
