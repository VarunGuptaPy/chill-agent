"""Base protocol for image generation providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Tuple


@dataclass
class ImageResult:
    path: Path
    width: int
    height: int
    prompt_used: str


class ImageProvider(Protocol):
    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: Tuple[int, int] = (1920, 1080),
    ) -> ImageResult: ...
