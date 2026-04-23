"""Stage 4: Image generation — content-driven images per segment + thumbnail, with NSFW safety."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.services.image.base import ImageProvider, ImageResult
from chill_agent.services.llm.base import LLMProvider
from chill_agent.stages.script import Script
from chill_agent.utils.paths import (
    images_dir,
    segment_sub_image_path,
    thumbnail_raw_path,
)

logger = structlog.get_logger()

_STYLE_SUFFIX_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "style_suffix.txt"
)

# Safety suffix appended to every prompt sent to the model
# NOTE: avoid NSFW keywords (nudity/blood/etc.) even when negated — Flux flags them regardless
_SAFETY_SUFFIX = ", safe for work, family friendly, all ages, cartoon style"

# Blocklist — any prompt containing these terms is replaced with a safe fallback
_NSFW_BLOCKLIST = [
    "nude", "naked", "nsfw", "porn", "sex", "erotic", "lingerie",
    "bikini", "underwear", "topless", "breast", "genitalia", "buttocks",
    "seductive", "provocative", "sensual", "intimate", "fetish",
    "gore", "blood", "dismember", "torture", "mutilat", "decapitat",
    "drug", "cocaine", "heroin", "meth", "syringe",
    "rifle", "pistol", "knife attack",
    "racist", "nazi", "swastika", "hate",
    "child abuse", "minor", "underage",
]

_SAFE_FALLBACK_PROMPT = "stick figure character standing and looking curious, simple background"


@dataclass
class ImagesResult:
    # List of lists — outer index = segment, inner = per-image paths
    segment_image_paths: List[List[Path]]
    thumbnail_path: Path
    total_images: int


def generate_images(
    image_provider: ImageProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    llm: Optional[LLMProvider] = None,
    force: bool = False,
    max_workers: int = 1,
) -> ImagesResult:
    """Generate content-driven images per segment + thumbnail. Sequential by default (rate-limit safe)."""

    style_suffix = _STYLE_SUFFIX_PATH.read_text(encoding="utf-8").strip()

    # Build flat task list: (seg_idx, img_idx, prompt, out_path, aspect_ratio)
    tasks = []
    for seg_idx, seg in enumerate(script.segments):
        for img_idx, scene_prompt in enumerate(seg.image_prompts):
            out_path = segment_sub_image_path(output_root, run_id, seg_idx, img_idx)
            prompt = _build_prompt(scene_prompt, style_suffix, llm)
            tasks.append(("segment", seg_idx, img_idx, prompt, out_path, "16:9"))

    # Thumbnail
    thumb_path = thumbnail_raw_path(output_root, run_id)
    thumb_prompt = _build_prompt(script.thumbnail_prompt, style_suffix, llm)
    tasks.append(("thumbnail", -1, 0, thumb_prompt, thumb_path, "16:9"))

    # Prepare result structure
    seg_images: List[List[Optional[Path]]] = [
        [None] * len(seg.image_prompts) for seg in script.segments
    ]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for task_type, seg_idx, img_idx, prompt, out_path, aspect_ratio in tasks:
            if out_path.exists() and not force:
                logger.debug("image_cache_hit", seg=seg_idx, img=img_idx)
                if task_type == "segment":
                    seg_images[seg_idx][img_idx] = out_path
                continue

            future = executor.submit(_generate_one, image_provider, prompt, out_path, aspect_ratio)
            futures[future] = (task_type, seg_idx, img_idx, out_path)

        for future in as_completed(futures):
            task_type, seg_idx, img_idx, out_path = futures[future]
            try:
                result = future.result()
                if task_type == "segment":
                    seg_images[seg_idx][img_idx] = result.path
                logger.info(
                    "image_generated",
                    type=task_type,
                    seg=seg_idx,
                    img=img_idx,
                    path=str(result.path),
                )
            except Exception as e:
                logger.error(
                    "image_generation_failed",
                    type=task_type,
                    seg=seg_idx,
                    img=img_idx,
                    error=str(e),
                )
                raise

    # Fill any remaining cache hits (paths that existed, not in futures)
    for seg_idx, seg in enumerate(script.segments):
        for img_idx in range(len(seg.image_prompts)):
            if seg_images[seg_idx][img_idx] is None:
                p = segment_sub_image_path(output_root, run_id, seg_idx, img_idx)
                seg_images[seg_idx][img_idx] = p

    # Clean: filter None, ensure each segment has at least one path
    clean_seg_images: List[List[Path]] = []
    total = 0
    for seg_idx, imgs in enumerate(seg_images):
        paths = [p for p in imgs if p is not None]
        if not paths:
            paths = [segment_sub_image_path(output_root, run_id, seg_idx, 0)]
        clean_seg_images.append(paths)
        total += len(paths)

    logger.info(
        "images_done",
        segments=len(clean_seg_images),
        total_images=total,
        thumbnail=str(thumb_path),
    )

    return ImagesResult(
        segment_image_paths=clean_seg_images,
        thumbnail_path=thumb_path,
        total_images=total + 1,
    )


def _build_prompt(scene_prompt: str, style_suffix: str, llm: Optional[LLMProvider] = None) -> str:
    """Assemble final prompt: style first, then scene, then safety suffix."""
    safe_scene = _sanitize_prompt(scene_prompt, llm)
    return f"{style_suffix}. Scene: {safe_scene}{_SAFETY_SUFFIX}"


def _sanitize_prompt(prompt: str, llm: Optional[LLMProvider] = None) -> str:
    """Block NSFW terms. If LLM is available, regenerate a safe version in real-time."""
    lower = prompt.lower()
    for term in _NSFW_BLOCKLIST:
        if term in lower:
            logger.warning("nsfw_prompt_blocked", term=term, prompt=prompt[:100])
            if llm is not None:
                try:
                    result = llm.complete(
                        system=(
                            "You write image prompts for a family-friendly educational YouTube channel. "
                            "Respond with ONLY the rewritten prompt — no explanation, no quotes."
                        ),
                        user=(
                            f"Rewrite this image prompt to be completely safe for work. "
                            f"Remove or replace any sensitive content while preserving the core visual concept "
                            f"(the scene, the characters, the action). Keep it under 30 words.\n\n"
                            f"Original prompt: {prompt}"
                        ),
                        temperature=0.7,
                        json_mode=False,
                        max_tokens=80,
                    )
                    rewritten = result.content.strip()
                    logger.info("nsfw_prompt_rewritten", original=prompt[:80], rewritten=rewritten[:80])
                    return rewritten
                except Exception as e:
                    logger.warning("nsfw_prompt_rewrite_failed", error=str(e))
            return _SAFE_FALLBACK_PROMPT
    return prompt


def _generate_one(
    provider: ImageProvider,
    prompt: str,
    output_path: Path,
    aspect_ratio: str,
) -> ImageResult:
    return provider.generate(prompt=prompt, output_path=output_path, aspect_ratio=aspect_ratio)
