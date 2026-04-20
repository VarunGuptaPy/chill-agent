"""Stage 2: Script generation — writes the full countdown script via DeepSeek."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.services.llm.base import LLMProvider

logger = structlog.get_logger()

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "script.md"

_SYSTEM_PROMPT = (
    "You are a YouTube script writer for a viral educational-entertainment channel. "
    "Write in an energetic, sarcastic, smart-casual voice. "
    "Always respond with valid JSON only."
)

_BANNED_PATTERNS = [
    r"\bfuck\b", r"\bshit\b", r"\bkill\s+yourself\b",
    r"\bn.gger\b", r"\bfaggot\b",
    r"(?i)graphic\s+(gore|violence)",
    r"(?i)explicit\s+sex",
]


@dataclass
class ScriptSegment:
    number: int
    label: str
    narration: str
    image_prompt: str


@dataclass
class Script:
    title: str
    description: str
    tags: List[str]
    thumbnail_prompt: str
    segments: List[ScriptSegment]
    outro: str
    raw_json: str = field(default="", repr=False)
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0

    @property
    def full_narration(self) -> str:
        """Full narration text: intro marker + all segments + outro."""
        parts = ["Let's get right into it."]
        for seg in self.segments:
            parts.append(seg.narration)
        parts.append(self.outro)
        return "\n\n".join(parts)

    @property
    def word_count(self) -> int:
        return len(self.full_narration.split())

    @property
    def total_chars(self) -> int:
        return len(self.full_narration)


def generate_script(llm: LLMProvider, title: str, brief: str) -> Script:
    """Generate a full countdown script for the given title."""
    prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    user_prompt = prompt_template.replace("{title}", title).replace("{brief}", brief)

    result = llm.complete(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=1.3,
        json_mode=True,
        max_tokens=8192,
    )

    raw = result.content.strip()
    script = _parse_script(raw)
    script.llm_input_tokens = result.input_tokens
    script.llm_output_tokens = result.output_tokens

    # Content moderation
    _check_content(script)

    logger.info(
        "script_generated",
        title=script.title,
        segments=len(script.segments),
        word_count=script.word_count,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )

    return script


def _parse_script(raw: str) -> Script:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # Try to extract JSON from the response
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Could not parse script JSON: {e}\nRaw: {raw[:500]}")

    segments = []
    for seg_data in data.get("segments", []):
        segments.append(
            ScriptSegment(
                number=int(seg_data.get("number", 0)),
                label=str(seg_data.get("label", "")),
                narration=str(seg_data.get("narration", "")),
                image_prompt=str(seg_data.get("image_prompt", "")),
            )
        )

    # Sort segments descending by number (highest first — countdown format)
    segments.sort(key=lambda s: s.number, reverse=True)

    return Script(
        title=str(data.get("title", "Untitled")),
        description=str(data.get("description", "")),
        tags=list(data.get("tags", [])),
        thumbnail_prompt=str(data.get("thumbnail_prompt", "")),
        segments=segments,
        outro=str(data.get("outro", "That's all for today, I'll be making similar videos in the future. Subscribe to see them.")),
        raw_json=raw,
    )


def _check_content(script: Script) -> None:
    """Reject scripts with disallowed content."""
    full_text = script.full_narration.lower()
    for pattern in _BANNED_PATTERNS:
        if re.search(pattern, full_text, re.IGNORECASE):
            raise ValueError(
                f"Script failed content moderation: matched pattern '{pattern}'"
            )

    if script.word_count < 1000:
        raise ValueError(
            f"Script too short: {script.word_count} words (minimum 1000). "
            "DeepSeek may have truncated the output."
        )
