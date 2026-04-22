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

_MODERATION_SYSTEM = (
    "You are a content moderation assistant for a family-friendly YouTube channel. "
    "Be concise. Reply with ONLY 'SAFE' or 'UNSAFE: [reason]'."
)


@dataclass
class ScriptSegment:
    number: int
    label: str
    narration: str
    image_prompts: List[str]  # 2-4 prompts per segment (was image_prompt: str)


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

    # Layer 1: pattern-based content check
    _check_content(script)

    # Layer 2: LLM moderation (temperature=0 for deterministic output)
    _moderate_with_llm(llm, script)

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
        match = re.search(r"\{[\s\S]+\}", raw)
        if match:
            data = json.loads(match.group(0))
        else:
            raise ValueError(f"Could not parse script JSON: {e}\nRaw: {raw[:500]}")

    segments = []
    for seg_data in data.get("segments", []):
        # Handle both new array format and old single-string format gracefully
        raw_prompts = seg_data.get("image_prompts") or seg_data.get("image_prompt")
        if isinstance(raw_prompts, str):
            image_prompts = [raw_prompts]
        elif isinstance(raw_prompts, list):
            image_prompts = [str(p) for p in raw_prompts if p]
        else:
            image_prompts = ["stick figure character looking surprised"]

        # Ensure at least 1, cap at 8
        if not image_prompts:
            image_prompts = ["stick figure character looking surprised"]
        image_prompts = image_prompts[:8]

        segments.append(
            ScriptSegment(
                number=int(seg_data.get("number", 0)),
                label=str(seg_data.get("label", "")),
                narration=str(seg_data.get("narration", "")),
                image_prompts=image_prompts,
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
    """Reject scripts with disallowed content (fast pattern check)."""
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


def _moderate_with_llm(llm: LLMProvider, script: Script) -> None:
    """LLM-based moderation — catches nuanced issues patterns miss."""
    # Truncate to keep cost negligible (first 2000 chars is enough to judge tone)
    excerpt = script.full_narration[:2000]

    try:
        result = llm.complete(
            system=_MODERATION_SYSTEM,
            user=(
                f"Review this YouTube script excerpt for a family-friendly educational channel.\n"
                f"Does it contain: sexual content, graphic violence, hate speech, drug promotion, "
                f"or content inappropriate for general audiences?\n\n"
                f"Script excerpt:\n{excerpt}"
            ),
            temperature=0.0,
            json_mode=False,
            max_tokens=50,
        )
        verdict = result.content.strip().upper()
        if not verdict.startswith("SAFE"):
            raise ValueError(
                f"Script failed LLM moderation: {result.content.strip()[:200]}"
            )
        logger.debug("script_moderation_passed")
    except ValueError:
        raise
    except Exception as e:
        # Moderation API failure — log and continue rather than blocking the pipeline
        logger.warning("script_moderation_llm_error", error=str(e))
