"""Base protocol for image generation providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


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
        aspect_ratio: str = "16:9",
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> ImageResult: ...
