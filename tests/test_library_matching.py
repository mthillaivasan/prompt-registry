"""Drop L2 — services.library_matching.match_library tests.

Deterministic ranking: prompt_type filters, then score = topic overlap *
weight + (domain bonus if matched). Sort by score desc, ties broken by
created_at desc. No Claude calls — pure SQLAlchemy + Python.
"""

import json

from app.models import PromptLibrary
from services import library_matching
from services.library_matching import match_library


def _seed(db, entries: list[dict]):
    for e in entries:
        row = PromptLibrary(
            title=e["title"],
            full_text=e.get("full_text", "x"),
            summary=e.get("summary"),
            prompt_type=e["prompt_type"],
            input_type=e.get("input_type"),
            output_type=e.get("output_type"),
            domain=e.get("domain", "general"),
            source_provenance=e.get("source_provenance"),
            topic_coverage=json.dumps(e.get("topic_coverage", [])),
            classification_notes=e.get("classification_notes"),
            created_at=e.get("created_at", "2026-04-19T00:00:00Z"),
            updated_at=e.get("updated_at", "2026-04-19T00:00:00Z"),
        )
        db.add(row)
    db.commit()


def test_filters_to_requested_prompt_type(db):
    _seed(db, [
        {"title": "Ext A", "prompt_type": "Extraction"},
        {"title": "Class A", "prompt_type": "Classification"},
        {"title": "Ext B", "prompt_type": "Extraction"},
    ])
    result = match_library(db, prompt_type="Extraction")
    titles = [e.title for e, _ in result]
    assert "Class A" not in titles
    assert set(titles) == {"Ext A", "Ext B"}


def test_topic_overlap_drives_ranking(db):
    _seed(db, [
        {
            "title": "Two-overlap",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points", "topic_8_null_handling"],
        },
        {
            "title": "Zero-overlap",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_10_error_modes"],
        },
        {
            "title": "One-overlap",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points"],
        },
    ])
    result = match_library(
        db,
        prompt_type="Extraction",
        topic_coverage=["topic_6_data_points", "topic_8_null_handling"],
    )
    titles = [e.title for e, _ in result]
    assert titles == ["Two-overlap", "One-overlap", "Zero-overlap"]


def test_domain_match_breaks_tie_when_overlap_equal(db):
    _seed(db, [
        {
            "title": "Finance match",
            "prompt_type": "Extraction",
            "domain": "finance",
            "topic_coverage": ["topic_6_data_points"],
        },
        {
            "title": "General entry",
            "prompt_type": "Extraction",
            "domain": "general",
            "topic_coverage": ["topic_6_data_points"],
        },
    ])
    result = match_library(
        db,
        prompt_type="Extraction",
        domain="finance",
        topic_coverage=["topic_6_data_points"],
    )
    titles = [e.title for e, _ in result]
    assert titles[0] == "Finance match"


def test_topic_overlap_outweighs_domain_bonus(db):
    _seed(db, [
        {
            "title": "Domain match no overlap",
            "prompt_type": "Extraction",
            "domain": "finance",
            "topic_coverage": [],
        },
        {
            "title": "General with overlap",
            "prompt_type": "Extraction",
            "domain": "general",
            "topic_coverage": ["topic_6_data_points"],
        },
    ])
    result = match_library(
        db,
        prompt_type="Extraction",
        domain="finance",
        topic_coverage=["topic_6_data_points"],
    )
    # topic_coverage_weight (2.0) on one match > domain_match_weight (1.0)
    titles = [e.title for e, _ in result]
    assert titles[0] == "General with overlap"


def test_created_at_desc_breaks_ties_when_score_equal(db):
    _seed(db, [
        {
            "title": "Older",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points"],
            "created_at": "2026-04-01T00:00:00Z",
        },
        {
            "title": "Newer",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points"],
            "created_at": "2026-04-20T00:00:00Z",
        },
    ])
    result = match_library(
        db,
        prompt_type="Extraction",
        topic_coverage=["topic_6_data_points"],
    )
    titles = [e.title for e, _ in result]
    assert titles[0] == "Newer"


def test_default_limit_caps_at_three(db):
    library_matching._load_config.cache_clear()
    _seed(db, [
        {
            "title": f"E{i}",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points"],
            "created_at": f"2026-04-19T{i:02d}:00:00Z",
        }
        for i in range(6)
    ])
    result = match_library(
        db,
        prompt_type="Extraction",
        topic_coverage=["topic_6_data_points"],
    )
    assert len(result) == 3


def test_explicit_limit_overrides_default(db):
    _seed(db, [
        {"title": f"E{i}", "prompt_type": "Extraction"} for i in range(5)
    ])
    result = match_library(db, prompt_type="Extraction", limit=2)
    assert len(result) == 2


def test_zero_limit_returns_empty(db):
    _seed(db, [{"title": "E", "prompt_type": "Extraction"}])
    assert match_library(db, prompt_type="Extraction", limit=0) == []


def test_no_candidates_returns_empty(db):
    assert match_library(db, prompt_type="Extraction") == []


def test_score_is_attached_to_each_result(db):
    _seed(db, [{
        "title": "A",
        "prompt_type": "Extraction",
        "domain": "finance",
        "topic_coverage": ["topic_6_data_points", "topic_8_null_handling"],
    }])
    result = match_library(
        db,
        prompt_type="Extraction",
        domain="finance",
        topic_coverage=["topic_6_data_points", "topic_8_null_handling"],
    )
    assert len(result) == 1
    _, score = result[0]
    # 2 overlaps × 2.0 + 1.0 domain bonus = 5.0
    assert score == 5.0
