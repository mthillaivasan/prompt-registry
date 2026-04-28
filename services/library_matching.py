"""Match Brief Builder context against the prompt library (Drop L2).

Approach: deterministic tag overlap, no embeddings.

The library is small (tens of entries at L1/L2 scale, low hundreds at the
horizon I can see) and its matching signal is already curated — every
entry carries a `prompt_type`, a `domain`, and a hand- or Haiku-tagged
`topic_coverage` array. Ranking by overlap on those tags answers the
"users building similar briefs made these choices" question directly.

A semantic / embedding-based match would buy us nothing at this scale and
would add real cost: an ANN index (pgvector or a separate service), an
embedding pipeline on every library mutation, plus ranker non-determinism
that complicates testing. The deterministic path also keeps the
configuration-first discipline — the matching weights live in
seed/library_matching.yml, not in code.

Revisit when:
  - the library exceeds ~500 entries OR
  - users routinely approve matches whose topic_coverage tags differ from
    the brief's signalled topics (i.e. tag overlap stops correlating with
    approval).

Configuration: see seed/library_matching.yml.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.models import PromptLibrary

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "seed" / "library_matching.yml"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f) or {}


def _topic_coverage(entry: PromptLibrary) -> list[str]:
    try:
        return json.loads(entry.topic_coverage or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def _score(
    entry: PromptLibrary,
    requested_domain: str | None,
    requested_topics: set[str],
    cfg: dict,
) -> float:
    overlap = len(requested_topics & set(_topic_coverage(entry)))
    score = overlap * cfg.get("topic_coverage_weight", 2.0)
    if requested_domain and entry.domain == requested_domain:
        score += cfg.get("domain_match_weight", 1.0)
    return score


def match_library(
    db: Session,
    prompt_type: str,
    domain: str | None = None,
    topic_coverage: list[str] | None = None,
    limit: int | None = None,
) -> list[tuple[PromptLibrary, float]]:
    """Return up to `limit` library entries ranked for this brief context.

    Filtering: prompt_type must match exactly. (No cross-type matches —
    Extraction examples coaching a Classification brief is more confusing
    than helpful at this stage.)

    Ranking: see _score above. Returns (entry, score) pairs sorted by
    score desc, then by created_at desc.

    `limit=None` falls back to the configured default_top_n. `limit=0`
    returns an empty list. Negative limits are clamped to 0.
    """
    cfg = _load_config()
    if limit is None:
        limit = int(cfg.get("default_top_n", 3))
    if limit <= 0:
        return []

    requested_topics = set(topic_coverage or [])
    min_score = float(cfg.get("min_score", 0.0))

    candidates = (
        db.query(PromptLibrary)
        .filter(PromptLibrary.prompt_type == prompt_type)
        .all()
    )

    scored: list[tuple[float, str, PromptLibrary]] = []
    for c in candidates:
        s = _score(c, domain, requested_topics, cfg)
        if s < min_score:
            continue
        scored.append((s, c.created_at or "", c))

    # Sort: score desc, then created_at desc on ties (newest first).
    # Python's sort is stable, so apply secondary key first.
    scored.sort(key=lambda triple: triple[1], reverse=True)
    scored.sort(key=lambda triple: triple[0], reverse=True)

    return [(entry, score) for score, _, entry in scored[:limit]]


def _clear_config_cache_for_tests() -> None:
    """Reset the config cache. Test-only helper — exposed so a test can
    reload after editing seed/library_matching.yml mid-suite. Callers in
    production code should never need this."""
    _load_config.cache_clear()
