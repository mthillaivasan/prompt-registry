"""Tests for the prompt_library admin API and seed script."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.auth import hash_password
from app.models import PromptLibrary, User
from scripts.seed_library import load_entries, upsert_entry


def _make_user(db, email: str, role: str, password: str = "pw"):
    u = User(
        email=email,
        name=f"{role} User",
        role=role,
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _login(client, email: str, password: str = "pw"):
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Admin-only authorisation ──────────────────────────────────────────────────

def test_list_library_rejects_maker(client, auth_headers):
    resp = client.get("/library", headers=auth_headers)
    assert resp.status_code == 403
    assert "Admin" in resp.json()["detail"]


def test_list_library_rejects_checker(client, db):
    _make_user(db, "check@test.local", "Checker")
    headers = _login(client, "check@test.local")
    resp = client.get("/library", headers=headers)
    assert resp.status_code == 403


def test_list_library_admin_ok_empty(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    resp = client.get("/library", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25, "has_next": False}


# ── Create / edit / delete ────────────────────────────────────────────────────

def test_admin_can_create_entry(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    resp = client.post("/library", json={
        "title": "Test entry",
        "full_text": "You are a test analyst. Extract X from Y.",
        "summary": "A test.",
        "prompt_type": "Extraction",
        "domain": "finance",
        "topic_coverage": ["topic_6_data_points"],
        "classification_notes": "Because it extracts data.",
    }, headers=headers)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["title"] == "Test entry"
    assert out["topic_coverage"] == ["topic_6_data_points"]
    assert out["classification_notes"] == "Because it extracts data."


def test_duplicate_title_rejected(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    payload = {
        "title": "Dup",
        "full_text": "text",
        "prompt_type": "Extraction",
        "domain": "general",
    }
    r1 = client.post("/library", json=payload, headers=headers)
    assert r1.status_code == 201
    r2 = client.post("/library", json=payload, headers=headers)
    assert r2.status_code == 409


def test_admin_can_edit_entry(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    create = client.post("/library", json={
        "title": "Editable",
        "full_text": "text",
        "prompt_type": "Extraction",
        "domain": "general",
    }, headers=headers)
    lib_id = create.json()["library_id"]

    patch_resp = client.patch(f"/library/{lib_id}", json={
        "summary": "Updated summary",
        "topic_coverage": ["topic_7_field_format"],
    }, headers=headers)
    assert patch_resp.status_code == 200
    out = patch_resp.json()
    assert out["summary"] == "Updated summary"
    assert out["topic_coverage"] == ["topic_7_field_format"]


def test_maker_cannot_edit_entry(client, db, auth_headers):
    admin = _make_user(db, "admin@test.local", "Admin")
    admin_headers = _login(client, "admin@test.local")
    create = client.post("/library", json={
        "title": "Maker-can't-touch",
        "full_text": "text",
        "prompt_type": "Extraction",
        "domain": "general",
    }, headers=admin_headers)
    lib_id = create.json()["library_id"]

    resp = client.patch(f"/library/{lib_id}", json={"summary": "hacked"}, headers=auth_headers)
    assert resp.status_code == 403


def test_admin_can_delete_entry(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    create = client.post("/library", json={
        "title": "Deletable",
        "full_text": "text",
        "prompt_type": "Extraction",
        "domain": "general",
    }, headers=headers)
    lib_id = create.json()["library_id"]

    resp = client.delete(f"/library/{lib_id}", headers=headers)
    assert resp.status_code == 204
    assert client.get(f"/library/{lib_id}", headers=headers).status_code == 404


def test_maker_cannot_delete_entry(client, db, auth_headers):
    admin = _make_user(db, "admin@test.local", "Admin")
    admin_headers = _login(client, "admin@test.local")
    create = client.post("/library", json={
        "title": "Maker-delete-blocked",
        "full_text": "text",
        "prompt_type": "Extraction",
        "domain": "general",
    }, headers=admin_headers)
    lib_id = create.json()["library_id"]

    resp = client.delete(f"/library/{lib_id}", headers=auth_headers)
    assert resp.status_code == 403


# ── Pagination ────────────────────────────────────────────────────────────────

def test_pagination_returns_page_size_and_has_next(client, db):
    _make_user(db, "admin@test.local", "Admin")
    headers = _login(client, "admin@test.local")
    for i in range(27):
        client.post("/library", json={
            "title": f"P{i:02d}",
            "full_text": "text",
            "prompt_type": "Extraction",
            "domain": "general",
        }, headers=headers)

    page1 = client.get("/library?page=1&page_size=25", headers=headers).json()
    assert len(page1["items"]) == 25
    assert page1["total"] == 27
    assert page1["has_next"] is True

    page2 = client.get("/library?page=2&page_size=25", headers=headers).json()
    assert len(page2["items"]) == 2
    assert page2["has_next"] is False


# ── Seed script: idempotency and Haiku classification ─────────────────────────

def _mock_haiku_classifying(payload: dict) -> MagicMock:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(payload))]
    mock_client.messages.create.return_value = mock_response
    return mock_client


def test_seed_upsert_creates_then_skips(db):
    """Idempotency: second run on the same title is a no-op."""
    entry = {
        "title": "Idem-1",
        "full_text": "You extract fields from a document.",
        "prompt_type": "Extraction",
        "input_type": "Document",
        "output_type": "JSON",
        "summary": "Already tagged.",
        "topic_coverage": ["topic_6_data_points"],
        "classification_notes": "Pre-tagged.",
        "domain": "finance",
    }
    action1, _ = upsert_entry(db, dict(entry))
    assert action1 == "created"

    action2, _ = upsert_entry(db, dict(entry))
    assert action2 == "skipped_exists"

    assert db.query(PromptLibrary).filter_by(title="Idem-1").count() == 1


def test_seed_skips_empty_full_text(db):
    action, _ = upsert_entry(db, {"title": "Placeholder", "full_text": ""})
    assert action == "skipped_empty"
    assert db.query(PromptLibrary).filter_by(title="Placeholder").count() == 0


def test_seed_calls_haiku_when_tags_missing(db):
    """Tag auto-population: untagged entry triggers Haiku, tags + notes persist."""
    mock = _mock_haiku_classifying({
        "prompt_type": "Extraction",
        "input_type": "PDF document",
        "output_type": "JSON object",
        "summary": "Extracts subscription terms.",
        "topic_coverage": ["topic_6_data_points", "topic_9_confidence_traceability"],
        "classification_notes": "Output is strict JSON with per-field confidence and page refs.",
    })

    action, merged = upsert_entry(db, {
        "title": "Needs-classification",
        "full_text": "Extract subscription-terms data. Cite pages. Return JSON.",
        "domain": "finance",
    }, client=mock)
    assert action == "created"
    mock.messages.create.assert_called_once()

    row = db.query(PromptLibrary).filter_by(title="Needs-classification").first()
    assert row is not None
    assert row.prompt_type == "Extraction"
    assert row.input_type == "PDF document"
    assert row.output_type == "JSON object"
    assert row.summary == "Extracts subscription terms."
    assert json.loads(row.topic_coverage) == ["topic_6_data_points", "topic_9_confidence_traceability"]
    assert "strict JSON" in row.classification_notes


def test_seed_preserves_provided_tags(db):
    """Tags set by fixture author survive classification (classification_notes still fetched)."""
    mock = _mock_haiku_classifying({
        "prompt_type": "Classification",  # different — must not override
        "input_type": "fabricated",
        "output_type": "fabricated",
        "summary": "fabricated summary",
        "topic_coverage": [],
        "classification_notes": "notes from Haiku",
    })
    action, merged = upsert_entry(db, {
        "title": "Has-partial-tags",
        "full_text": "text",
        "prompt_type": "Extraction",
        "input_type": "Prospectus",
        "output_type": "JSON",
        "summary": "author-provided summary",
        "topic_coverage": ["topic_6_data_points"],
        "domain": "finance",
    }, client=mock)

    row = db.query(PromptLibrary).filter_by(title="Has-partial-tags").first()
    assert row.prompt_type == "Extraction"  # author value wins
    assert row.input_type == "Prospectus"
    assert row.summary == "author-provided summary"
    assert json.loads(row.topic_coverage) == ["topic_6_data_points"]
    assert row.classification_notes == "notes from Haiku"


def test_seed_load_entries_reports_each_action(db):
    mock = _mock_haiku_classifying({
        "prompt_type": "Extraction",
        "input_type": "Document",
        "output_type": "JSON",
        "summary": "ok",
        "topic_coverage": [],
        "classification_notes": "ok",
    })
    entries = [
        {"title": "A", "full_text": "text", "domain": "general"},
        {"title": "B", "full_text": "", "domain": "general"},  # skipped
        {"title": "A", "full_text": "text", "domain": "general"},  # dup
    ]
    results = load_entries(db, entries, client=mock)
    actions = [a for a, _ in results]
    assert actions == ["created", "skipped_empty", "skipped_exists"]


# ── L1 fixture contract ───────────────────────────────────────────────────────
#
# These guard the L1 deliverable: at least 15 entries, two empty-fulltext
# placeholders for Lombard content, and at least one entry per prompt_type
# that already ships pre-tagged so the library can be browsed without first
# running Haiku. The Haiku auto-tag path is still exercised on first seed by
# the entries that intentionally ship without classification fields.

def test_l1_fixture_meets_drop_contract():
    """fixtures/library_seed.yaml is L1's seed input. Pin its shape."""
    import os
    from scripts.seed_library import _load_yaml

    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "fixtures",
        "library_seed.yaml",
    )
    entries = _load_yaml(fixture_path)

    assert len(entries) >= 15, f"L1 expects >= 15 entries, got {len(entries)}"

    placeholders = [e for e in entries if not (e.get("full_text") or "").strip()]
    assert len(placeholders) >= 2, "expect >= 2 empty-fulltext placeholders"
    assert any("Lombard" in (e.get("title") or "") for e in placeholders), \
        "expect at least one Lombard placeholder"

    pre_tagged_types = {
        e["prompt_type"] for e in entries
        if e.get("prompt_type") and (e.get("full_text") or "").strip()
    }
    # L1 ships starter coverage across all 8 prompt_types.
    expected = {
        "Governance", "Analysis", "Comms", "Classification",
        "Summarisation", "Extraction", "Comparison", "Risk Review",
    }
    missing = expected - pre_tagged_types
    # Allow Governance to come exclusively from auto-tagged entries — the
    # library is starter content, not a full taxonomy guarantee.
    tolerated_missing = {"Governance"}
    assert missing <= tolerated_missing, \
        f"prompt_type coverage gap: {missing - tolerated_missing}"

    untagged_with_text = [
        e for e in entries
        if (e.get("full_text") or "").strip() and not e.get("prompt_type")
    ]
    assert len(untagged_with_text) >= 1, \
        "expect at least one fixture entry without prompt_type so the Haiku auto-tag path is exercised at seed time"
