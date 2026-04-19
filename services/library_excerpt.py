"""Per-topic excerpt extraction from prompt_library full_text.

Used by GET /library/relevant to surface the paragraph(s) from a reference
prompt that address a specific Brief Builder topic — without sending the
whole prompt body to the UI or to Claude's few-shot context.

Implementation is deterministic keyword scoring. Each prose topic has a
set of cue phrases; paragraphs are scored by the number of distinct cues
they contain, plus small bonuses for density. The top-scoring paragraph
above a minimum threshold is returned; otherwise None.

Structured topics (1-5, 4b) return None — there is no meaningful prose
excerpt to pull for a pick-from-list topic.

No Claude calls. Zero cost per request.
"""

from __future__ import annotations

import re

# ── Cue phrase map — prose topics only ───────────────────────────────────────
# Phrases are matched case-insensitively as substrings. Keep these short and
# domain-neutral; the library will grow and cues should remain robust across
# prompt types beyond Extraction.

_CUES_BY_TOPIC: dict[str, tuple[str, ...]] = {
    "topic_6_data_points": (
        "field",
        "extract",
        "data point",
        "values",
        "column",
    ),
    "topic_7_field_format": (
        "format",
        "normalisation",
        "normalization",
        "timezone",
        "time zone",
        "decimal",
        "iso",
        "currency",
        "convention",
        "unit",
    ),
    "topic_8_null_handling": (
        "null",
        "missing",
        "not found",
        "not present",
        "not stated",
        "absent",
        "not available",
        "no value",
        "unknown",
    ),
    "topic_9_confidence_traceability": (
        "confidence",
        "cite",
        "citation",
        "source page",
        "page reference",
        "page number",
        "section heading",
        "traceability",
        "provenance",
    ),
    "topic_10_error_modes": (
        "error",
        "exception",
        "conflict",
        "malformed",
        "partial",
        "fail loudly",
        "contradict",
        "out of scope",
        "invalid",
    ),
}

# Paragraphs under this score are considered noise. A score of 1 means the
# paragraph mentions the topic only in passing (e.g. the word "field" in a
# prompt that does not meaningfully address data points). 2+ gives two
# distinct cue hits or one high-signal cue — strong enough to be useful.
_MIN_SCORE = 2

# Paragraph character cap — extracts longer than this are truncated with "…"
# to keep the UI legible and the few-shot context short.
_MAX_CHARS = 500


def _paragraphs(text: str) -> list[str]:
    """Split by blank-line separators; preserve internal newlines."""
    # Normalise CRLF, then split on two-or-more consecutive newlines
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = re.split(r"\n{2,}", normalised)
    return [p.strip() for p in parts if p.strip()]


def _score_paragraph(paragraph: str, cues: tuple[str, ...]) -> int:
    """Count distinct cue substrings present in the paragraph."""
    lower = paragraph.lower()
    hits = sum(1 for cue in cues if cue in lower)
    return hits


def _truncate(text: str, cap: int = _MAX_CHARS) -> str:
    if len(text) <= cap:
        return text
    # Truncate at a word boundary if possible, within the cap
    trimmed = text[:cap].rsplit(" ", 1)[0]
    return trimmed.rstrip(",;:. ") + "…"


def extract_topic_excerpt(full_text: str, topic_id: str) -> str | None:
    """Return the best paragraph matching `topic_id`, or None if nothing
    scores above the minimum threshold. Structured topics always return None.
    """
    if not full_text or not full_text.strip():
        return None

    cues = _CUES_BY_TOPIC.get(topic_id)
    if not cues:
        return None  # structured or unknown topic — no excerpt available

    best: tuple[int, str] | None = None
    for para in _paragraphs(full_text):
        score = _score_paragraph(para, cues)
        if score < _MIN_SCORE:
            continue
        if best is None or score > best[0]:
            best = (score, para)

    if best is None:
        return None

    return _truncate(best[1])


def is_prose_topic(topic_id: str) -> bool:
    """True if this topic supports excerpt extraction at all."""
    return topic_id in _CUES_BY_TOPIC
