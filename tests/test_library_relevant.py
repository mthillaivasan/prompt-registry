"""Tests for GET /library/relevant — few-shot feeder for validate-topic."""

import json

from app.auth import hash_password
from app.models import PromptLibrary, User


def _make_user(db, email: str, role: str, password: str = "pw"):
    u = User(
        email=email, name=f"{role} User", role=role,
        password_hash=hash_password(password), is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(client, email: str, password: str = "pw"):
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _seed_library(db, entries: list[dict]):
    for e in entries:
        row = PromptLibrary(
            title=e["title"],
            full_text=e["full_text"],
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


# ── Access control ────────────────────────────────────────────────────────────

def test_relevant_requires_auth(client):
    resp = client.get("/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points")
    assert resp.status_code == 401


def test_maker_can_read_relevant(client, auth_headers, db):
    _seed_library(db, [{
        "title": "Example",
        "full_text": "Extract fields from the prospectus. Name each field and its expected type.",
        "prompt_type": "Extraction",
        "topic_coverage": ["topic_6_data_points"],
    }])
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Example"
    assert "excerpt" in body[0]
    assert "fields" in body[0]["excerpt"].lower()


# ── Filter and ordering ───────────────────────────────────────────────────────

def test_prompt_type_filter_excludes_others(client, auth_headers, db):
    _seed_library(db, [
        {
            "title": "Ext entry",
            "full_text": "Extract fields. Name each field, its type, and rough source location.",
            "prompt_type": "Extraction",
        },
        {
            "title": "Class entry",
            "full_text": "Extract fields. Name each field, its type, and rough source location.",
            "prompt_type": "Classification",
        },
    ])
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points",
        headers=auth_headers,
    )
    titles = [e["title"] for e in resp.json()]
    assert titles == ["Ext entry"]


def test_topic_coverage_hits_rank_first(client, auth_headers, db):
    _seed_library(db, [
        {
            "title": "No coverage",
            "full_text": "Extract fields and list each field's source column.",
            "prompt_type": "Extraction",
            "topic_coverage": [],  # no tag
            "created_at": "2026-04-19T10:00:00Z",
        },
        {
            "title": "Tagged for topic",
            "full_text": "Extract fields. Name each field and its expected type.",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_6_data_points"],
            "created_at": "2026-04-19T09:00:00Z",  # older — should still rank first
        },
    ])
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points",
        headers=auth_headers,
    )
    titles = [e["title"] for e in resp.json()]
    assert titles[0] == "Tagged for topic"


def test_entries_without_matching_excerpt_dropped(client, auth_headers, db):
    _seed_library(db, [
        {
            "title": "Poem",
            "full_text": "Write a poem about clouds.",  # no null cues
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_8_null_handling"],
        },
        {
            "title": "Real null policy",
            "full_text": "For fields not found in the source, render 'not stated' and mark confidence low.",
            "prompt_type": "Extraction",
        },
    ])
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_8_null_handling",
        headers=auth_headers,
    )
    titles = [e["title"] for e in resp.json()]
    assert titles == ["Real null policy"]


def test_empty_list_when_nothing_matches(client, auth_headers, db):
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json() == []


def test_limit_caps_results(client, auth_headers, db):
    entries = [
        {
            "title": f"E{i}",
            "full_text": "Extract fields. Name each field and type.",
            "prompt_type": "Extraction",
            "created_at": f"2026-04-19T{i:02d}:00:00Z",
        }
        for i in range(5)
    ]
    _seed_library(db, entries)
    resp = client.get(
        "/library/relevant?prompt_type=Extraction&topic_id=topic_6_data_points&limit=2",
        headers=auth_headers,
    )
    assert len(resp.json()) == 2
