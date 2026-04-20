"""Background music selection — rotates royalty-free tracks."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


def pick_music_track(music_dir: Path) -> Optional[Path]:
    """Return a random music track from the music directory.

    Returns None if no tracks are found (music will be skipped).
    """
    if not music_dir.exists():
        logger.warning("music_dir_not_found", path=str(music_dir))
        return None

    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    # Exclude metadata files
    tracks = [t for t in tracks if not t.name.startswith(".") and t.name != "SOURCES.md"]

    if not tracks:
        logger.warning(
            "no_music_tracks",
            music_dir=str(music_dir),
            message="Drop royalty-free MP3/WAV files in assets/music/ to enable background music.",
        )
        return None

    track = random.choice(tracks)
    logger.info("music_selected", track=track.name)
    return track
