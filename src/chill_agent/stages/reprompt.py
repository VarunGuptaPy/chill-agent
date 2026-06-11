"""Stage: reprompt — regenerate image prompts for each segment without touching narration or audio.

Useful when:
- Image prompts from the script stage are vague or low-quality
- The style_suffix changed and you want new prompts generated to match
- You want to resume after TTS but regenerate images with fresh prompts
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from chill_agent.services.llm.base import LLMProvider
from chill_agent.stages.script import Script, ScriptSegment

logger = structlog.get_logger()

_REPROMPT_SYSTEM = (
    "You generate image prompts for a YouTube educational cartoon channel. "
    "The character is a Cyanide-and-Happiness-style stick figure. "
    "Respond with valid JSON only."
)

_SEGMENT_PROMPT = """\
You are generating image prompts for a YouTube countdown video segment.

Segment label: {label}
Narration:
{narration}

Generate image prompts that visually illustrate this narration beat-by-beat, like b-roll cuts in a YouTube video.
Each time the narration shifts to a new idea, analogy, example, step, fact, or joke — that is a new image.
The viewer should NEVER stare at the same image for more than 15–20 seconds.

MINIMUM REQUIREMENT: Generate at least 10 image prompts per segment. A 300-word segment needs 10–14 images. \
A 400-word segment needs 12–16 images. More is better — err on the side of too many.

Rules:
- Each prompt must be a clear, specific scene description under 35 words
- Use actual names for real things: if the narration mentions Gol Gumbaz, write "Gol Gumbaz"; \
if it mentions the Mariana Trench, write "Mariana Trench"; never replace a specific thing with a generic description
- Include a stick figure character in most images doing something relevant to the narration beat
- Every image must show a VISUALLY DISTINCT scene — different location, pose, action, or subject from all others in this segment
- Describe the scene only — do NOT mention art style
- Match each image to the exact beat of narration: explanation → show it; analogy → show the analogy; punchline → show the reaction; statistic → show the scale

Return ONLY a JSON object:
{{
  "image_prompts": ["prompt 1", "prompt 2", ...]
}}
"""

_THUMBNAIL_PROMPT = """\
Generate a thumbnail image prompt for this video:

Title: {title}
Topic: {brief}

The thumbnail should show a group of 4–5 stick figure characters with round white heads,
each doing something different that relates to the video topic. Exaggerated expressions,
chaotic fun composition. Make it immediately intriguing.

Return ONLY a JSON object:
{{"thumbnail_prompt": "your prompt here"}}
"""


def reprompt_images(
    llm: LLMProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    topic_brief: str = "",
    force: bool = False,
) -> Script:
    """Regenerate image prompts for every segment + thumbnail using the LLM.

    The narration text is untouched — only image_prompts on each segment and
    thumbnail_prompt on the script are replaced. The updated script is written
    back to script.json so downstream stages (images, assembly) pick it up.
    """
    script_cache = output_root / run_id / "script.json"

    if not force and _all_prompts_look_good(script):
        logger.info("reprompt_skipped_prompts_look_fine", run_id=run_id)
        return script

    updated_segments = []
    total_input = 0
    total_output = 0

    for seg in script.segments:
        user_msg = _SEGMENT_PROMPT.format(
            label=seg.label,
            narration=seg.narration.strip(),
        )
        result = llm.complete(
            system=_REPROMPT_SYSTEM,
            user=user_msg,
            temperature=0.9,
            json_mode=True,
            max_tokens=2048,
        )
        total_input += result.input_tokens
        total_output += result.output_tokens

        try:
            data = json.loads(result.content)
            new_prompts = [
                str(p).strip() for p in data.get("image_prompts", [])
                if p and len(str(p).strip()) >= 8
            ]
        except Exception as exc:
            logger.warning(
                "reprompt_parse_failed",
                segment=seg.label,
                error=str(exc),
            )
            new_prompts = seg.image_prompts  # keep originals on failure

        if not new_prompts:
            new_prompts = seg.image_prompts

        logger.info(
            "reprompt_segment_done",
            segment=seg.label,
            prompt_count=len(new_prompts),
        )

        updated_segments.append(
            ScriptSegment(
                number=seg.number,
                label=seg.label,
                narration=seg.narration,
                image_prompts=new_prompts,
            )
        )

    # Regenerate thumbnail prompt
    thumb_result = llm.complete(
        system=_REPROMPT_SYSTEM,
        user=_THUMBNAIL_PROMPT.format(title=script.title, brief=topic_brief or script.title),
        temperature=0.9,
        json_mode=True,
        max_tokens=256,
    )
    total_input += thumb_result.input_tokens
    total_output += thumb_result.output_tokens

    try:
        thumb_data = json.loads(thumb_result.content)
        new_thumbnail_prompt = str(thumb_data.get("thumbnail_prompt", "")).strip()
    except Exception:
        new_thumbnail_prompt = script.thumbnail_prompt

    if not new_thumbnail_prompt:
        new_thumbnail_prompt = script.thumbnail_prompt

    updated_script = Script(
        title=script.title,
        description=script.description,
        tags=script.tags,
        thumbnail_prompt=new_thumbnail_prompt,
        segments=updated_segments,
        outro=script.outro,
        raw_json=script.raw_json,
        llm_input_tokens=script.llm_input_tokens + total_input,
        llm_output_tokens=script.llm_output_tokens + total_output,
    )

    # Write back to disk so images stage and resume both see the fresh prompts
    _save_script_cache(updated_script, script_cache)

    logger.info(
        "reprompt_complete",
        run_id=run_id,
        segments=len(updated_segments),
        reprompt_input_tokens=total_input,
        reprompt_output_tokens=total_output,
    )

    return updated_script


def _all_prompts_look_good(script: Script) -> bool:
    """Heuristic: return False if any segment has suspicious/garbled prompts."""
    for seg in script.segments:
        for p in seg.image_prompts:
            s = p.strip()
            # Single words, digits, or JSON-like blobs are signs of corruption
            if len(s) < 12 or s[0] in ('{', '[') or s.isdigit():
                return False
    return True


def _save_script_cache(script: Script, path: Path) -> None:
    data = {
        "title": script.title,
        "description": script.description,
        "tags": script.tags,
        "thumbnail_prompt": script.thumbnail_prompt,
        "segments": [
            {
                "number": s.number,
                "label": s.label,
                "narration": s.narration,
                "image_prompts": s.image_prompts,
            }
            for s in script.segments
        ],
        "outro": script.outro,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
