"""Tests for services.library_excerpt — per-topic paragraph extraction."""

from services.library_excerpt import extract_topic_excerpt, is_prose_topic


# ── Per-topic positive cases ──────────────────────────────────────────────────

def test_topic_6_data_points_picks_field_list_paragraph():
    text = """You are an analyst.

Fields to extract include subscription cut-off time, ISIN, and minimum
investment amount. Each field must be labelled with its name.

Render output as a report.
"""
    ex = extract_topic_excerpt(text, "topic_6_data_points")
    assert ex is not None
    assert "Fields to extract" in ex
    assert "analyst" not in ex


def test_topic_7_field_format_picks_format_paragraph():
    text = """You are an analyst.

Report findings clearly.

Time values must use ISO 8601 format with timezone. Currency values
should use decimal notation with three-letter currency codes. Follow the
convention of the source document when normalisation is ambiguous.
"""
    ex = extract_topic_excerpt(text, "topic_7_field_format")
    assert ex is not None
    assert "ISO 8601" in ex
    assert "format" in ex.lower()


def test_topic_8_null_handling_picks_null_paragraph():
    text = """Extract each field.

If a value is not stated in the source, render "not found" and mark the
confidence low with a one-line note. Null values must never be silently
omitted.

Output as JSON.
"""
    ex = extract_topic_excerpt(text, "topic_8_null_handling")
    assert ex is not None
    assert "not stated" in ex or "null" in ex.lower()


def test_topic_9_confidence_traceability_picks_citation_paragraph():
    text = """Be accurate.

For every extracted value, cite the source page and section heading.
Assign a confidence tier (high / medium / low) based on clarity of the
source.

Return JSON.
"""
    ex = extract_topic_excerpt(text, "topic_9_confidence_traceability")
    assert ex is not None
    assert "page" in ex.lower() or "confidence" in ex.lower()


def test_topic_10_error_modes_picks_exception_paragraph():
    text = """Follow the ordered fields list.

Handle error modes explicitly: if the document is malformed, partial, or
contains conflicting values across pages, raise an exception and surface
the conflict to the reviewer rather than silently choosing one.

Output as JSON.
"""
    ex = extract_topic_excerpt(text, "topic_10_error_modes")
    assert ex is not None
    assert "malformed" in ex or "conflict" in ex


# ── No-match and edge cases ───────────────────────────────────────────────────

def test_no_matching_cues_returns_none():
    text = """Write a poem about clouds.

Make it whimsical and end with a rhyming couplet.
"""
    assert extract_topic_excerpt(text, "topic_8_null_handling") is None


def test_empty_text_returns_none():
    assert extract_topic_excerpt("", "topic_6_data_points") is None
    assert extract_topic_excerpt("   ", "topic_6_data_points") is None


def test_structured_topic_returns_none():
    text = """Extract fields. Return JSON. Handle nulls. Cite pages."""
    assert extract_topic_excerpt(text, "topic_1_prompt_type") is None
    assert extract_topic_excerpt(text, "topic_5_risk_tier") is None


def test_single_cue_below_threshold_returns_none():
    """One stray mention of 'field' should not trip the extractor."""
    text = "You are a field analyst covering European markets."
    assert extract_topic_excerpt(text, "topic_6_data_points") is None


def test_long_paragraph_is_truncated_with_ellipsis():
    long_para = (
        "Fields to extract include: "
        + ", ".join(f"field_{i} (type date, column {i})" for i in range(50))
    )
    ex = extract_topic_excerpt(long_para, "topic_6_data_points")
    assert ex is not None
    assert ex.endswith("…")
    assert len(ex) <= 501  # cap 500 + one char for ellipsis


def test_is_prose_topic():
    assert is_prose_topic("topic_6_data_points") is True
    assert is_prose_topic("topic_8_null_handling") is True
    assert is_prose_topic("topic_1_prompt_type") is False
    assert is_prose_topic("unknown") is False
