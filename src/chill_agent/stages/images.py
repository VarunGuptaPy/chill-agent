"""Stage 4: Image generation — generates one image per segment + thumbnail."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.services.image.base import ImageProvider, ImageResult
from chill_agent.stages.script import Script
from chill_agent.utils.paths import images_dir, segment_image_path, thumbnail_raw_path

logger = structlog.get_logger()

_STYLE_SUFFIX_PATH = (
    Path(__file__).parent.parent.parent.parent / "config" / "style_suffix.txt"
)


@dataclass
class ImagesResult:
    segment_image_paths: List[Path]
    thumbnail_path: Path
    total_images: int


def generate_images(
    image_provider: ImageProvider,
    script: Script,
    run_id: str,
    output_root: Path,
    force: bool = False,
    max_workers: int = 1,
) -> ImagesResult:
    """Generate all segment images + thumbnail in parallel."""

    style_suffix = _STYLE_SUFFIX_PATH.read_text(encoding="utf-8").strip()

    tasks = []

    # Segment images (1920×1080)
    for i, seg in enumerate(script.segments):
        out_path = segment_image_path(output_root, run_id, i)
        prompt = f"{seg.image_prompt}, {style_suffix}"
        tasks.append(("segment", i, prompt, out_path, (1920, 1080)))

    # Thumbnail (1280×720)
    thumb_path = thumbnail_raw_path(output_root, run_id)
    thumb_prompt = f"{script.thumbnail_prompt}, {style_suffix}"
    tasks.append(("thumbnail", -1, thumb_prompt, thumb_path, (1280, 720)))

    # Run in thread pool
    seg_paths = [None] * len(script.segments)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for task_type, idx, prompt, out_path, size in tasks:
            if out_path.exists() and not force:
                logger.debug("image_cache_hit", type=task_type, idx=idx, path=str(out_path))
                if task_type == "segment":
                    seg_paths[idx] = out_path
                continue

            future = executor.submit(
                _generate_one, image_provider, prompt, out_path, size
            )
            futures[future] = (task_type, idx, out_path)

        for future in as_completed(futures):
            task_type, idx, out_path = futures[future]
            try:
                result = future.result()
                if task_type == "segment":
                    seg_paths[idx] = result.path
                logger.info(
                    "image_generated",
                    type=task_type,
                    idx=idx,
                    path=str(result.path),
                )
            except Exception as e:
                logger.error(
                    "image_generation_failed",
                    type=task_type,
                    idx=idx,
                    error=str(e),
                )
                raise

    # Fill any cache hits that weren't in futures
    for i in range(len(script.segments)):
        if seg_paths[i] is None:
            seg_paths[i] = segment_image_path(output_root, run_id, i)

    # Handle thumbnail cache hit
    if not thumb_path.exists():
        thumb_path = thumbnail_raw_path(output_root, run_id)

    logger.info(
        "images_done",
        segment_images=len(seg_paths),
        thumbnail=str(thumb_path),
    )

    return ImagesResult(
        segment_image_paths=[p for p in seg_paths if p is not None],
        thumbnail_path=thumb_path,
        total_images=len(seg_paths) + 1,
    )


def _generate_one(
    provider: ImageProvider,
    prompt: str,
    output_path: Path,
    size: tuple,
) -> ImageResult:
    return provider.generate(prompt=prompt, output_path=output_path, size=size)
