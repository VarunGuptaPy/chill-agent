"""Base protocol for TTS providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class AudioResult:
    path: Path
    duration_seconds: float
    sample_rate: int
    chars_synthesized: int


class TTSProvider(Protocol):
    def synthesize(self, text: str, voice_id: str, output_path: Path) -> AudioResult: ...
