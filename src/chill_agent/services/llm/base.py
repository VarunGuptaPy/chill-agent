"""Base protocol for LLM providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class LLMResult:
    content: str
    input_tokens: int
    output_tokens: int
    model: str


class LLMProvider(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 1.0,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> LLMResult: ...
