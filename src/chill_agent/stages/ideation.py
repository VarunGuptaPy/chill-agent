"""Stage 1: Topic ideation — picks a fresh title using DeepSeek."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import structlog

from chill_agent.db.models import Topic
from chill_agent.services.llm.base import LLMProvider

logger = structlog.get_logger()

_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "config" / "prompts" / "ideation.md"

_SYSTEM_PROMPT = (
    "You are a YouTube content ideation assistant for a viral educational-entertainment channel. "
    "Always respond with valid JSON only."
)


@dataclass
class IdeationResult:
    title: str
    brief: str
    llm_input_tokens: int
    llm_output_tokens: int
    candidates: List[dict]


def ideate(
    llm: LLMProvider,
    past_topics: List[Topic],
    performance_stats: Optional[List[dict]] = None,
) -> IdeationResult:
    """Pick a fresh video topic, avoiding duplicates and weighting by performance."""

    past_titles = "\n".join(f"- {t.title}" for t in past_topics[:200])
    if not past_titles:
        past_titles = "(none yet)"

    prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    user_prompt = prompt_template.replace("{past_titles}", past_titles)

    result = llm.complete(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=1.0,
        json_mode=True,
    )

    raw = result.content.strip()

    # Parse — handle both {"candidates": [...]} and bare [...]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            candidates = data
        elif isinstance(data, dict):
            # Try common keys
            for key in ("candidates", "titles", "ideas", "results"):
                if key in data and isinstance(data[key], list):
                    candidates = data[key]
                    break
            else:
                # Grab first list value
                candidates = next(
                    (v for v in data.values() if isinstance(v, list)), []
                )
        else:
            candidates = []
    except json.JSONDecodeError as e:
        logger.error("ideation_json_parse_failed", raw=raw[:500], error=str(e))
        raise

    if not candidates:
        raise ValueError(f"DeepSeek returned no candidates. Raw: {raw[:300]}")

    # Deduplicate against past titles using cosine similarity (if sklearn available)
    past_title_strs = [t.title.lower() for t in past_topics]
    filtered = _filter_similar(candidates, past_title_strs)

    if not filtered:
        logger.warning("ideation_all_filtered", message="All candidates too similar to past. Using top candidate.")
        filtered = candidates[:1]

    # Score by performance prior if we have stats
    winner = _score_and_pick(filtered, performance_stats or [])

    logger.info(
        "ideation_done",
        title=winner["title"],
        candidates_total=len(candidates),
        candidates_after_filter=len(filtered),
    )

    return IdeationResult(
        title=winner["title"],
        brief=winner.get("brief", ""),
        llm_input_tokens=result.input_tokens,
        llm_output_tokens=result.output_tokens,
        candidates=candidates,
    )


def _filter_similar(candidates: List[dict], past_titles: List[str]) -> List[dict]:
    if not past_titles:
        return candidates

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        all_titles = past_titles + [c["title"].lower() for c in candidates]
        vectorizer = TfidfVectorizer(ngram_range=(1, 2)).fit(all_titles)
        past_vecs = vectorizer.transform(past_titles)
        candidate_vecs = vectorizer.transform([c["title"].lower() for c in candidates])

        filtered = []
        for i, cand in enumerate(candidates):
            sims = cosine_similarity(candidate_vecs[i : i + 1], past_vecs)
            max_sim = float(sims.max()) if sims.size > 0 else 0.0
            if max_sim < 0.82:
                filtered.append(cand)
            else:
                logger.debug(
                    "ideation_filtered_duplicate",
                    title=cand["title"],
                    max_similarity=round(max_sim, 3),
                )

        return filtered if filtered else candidates

    except ImportError:
        logger.warning("sklearn_not_available", message="Skipping similarity filter. Install scikit-learn.")
        return candidates


def _score_and_pick(candidates: List[dict], performance_stats: List[dict]) -> dict:
    """Pick the best candidate weighted by topic cluster performance."""
    if not performance_stats or not candidates:
        return candidates[0]

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        perf_titles = [s["title"].lower() for s in performance_stats]
        perf_scores = [s.get("views_per_hour", 0) for s in performance_stats]

        cand_titles = [c["title"].lower() for c in candidates]
        all_texts = perf_titles + cand_titles

        vectorizer = TfidfVectorizer(ngram_range=(1, 2)).fit(all_texts)
        perf_vecs = vectorizer.transform(perf_titles)
        cand_vecs = vectorizer.transform(cand_titles)

        scores = []
        for i in range(len(candidates)):
            sim = cosine_similarity(cand_vecs[i : i + 1], perf_vecs)
            weighted_score = float(np.dot(sim, perf_scores)) if sim.size > 0 else 0.0
            scores.append(weighted_score)

        best_idx = int(np.argmax(scores))
        return candidates[best_idx]

    except Exception as e:
        logger.warning("ideation_scoring_failed", error=str(e))
        return candidates[0]
