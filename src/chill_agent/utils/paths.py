"""Path helpers for consistent artifact layout."""

from __future__ import annotations

from pathlib import Path


def run_dir(output_root: Path, run_id: str) -> Path:
    d = output_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def images_dir(output_root: Path, run_id: str) -> Path:
    d = run_dir(output_root, run_id) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def audio_dir(output_root: Path, run_id: str) -> Path:
    d = run_dir(output_root, run_id) / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def video_dir(output_root: Path, run_id: str) -> Path:
    d = run_dir(output_root, run_id) / "video"
    d.mkdir(parents=True, exist_ok=True)
    return d


def segment_image_path(output_root: Path, run_id: str, idx: int) -> Path:
    return images_dir(output_root, run_id) / f"seg_{idx:02d}.png"


def thumbnail_raw_path(output_root: Path, run_id: str) -> Path:
    return images_dir(output_root, run_id) / "thumbnail_raw.png"


def segment_audio_path(output_root: Path, run_id: str, idx: int) -> Path:
    return audio_dir(output_root, run_id) / f"seg_{idx:02d}.mp3"


def full_audio_path(output_root: Path, run_id: str) -> Path:
    return audio_dir(output_root, run_id) / "full_narration.wav"


def srt_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "captions.srt"


def segment_video_path(output_root: Path, run_id: str, idx: int) -> Path:
    return video_dir(output_root, run_id) / f"seg_{idx:02d}.mp4"


def final_video_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "final.mp4"


def thumbnail_a_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "thumbnail_a.jpg"


def thumbnail_b_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "thumbnail_b.jpg"


def script_cache_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "script.json"


def alignment_cache_path(output_root: Path, run_id: str) -> Path:
    return run_dir(output_root, run_id) / "alignment.json"
