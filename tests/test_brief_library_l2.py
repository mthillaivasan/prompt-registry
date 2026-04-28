"""Drop L2 — Brief Builder library wiring tests.

Covers:
  - GET /briefs/{id}/library-matches: prompt_type derivation, domain
    derivation from client_name, approved flag round-trip.
  - PATCH /briefs/{id} approved_library_refs persistence.
  - GET /briefs/{id}/library-references: with topic_id (excerpts), without
    topic_id (full_text payload), 404 on missing brief.
  - generation: reference_examples reach the user message; empty list
    leaves the prompt unchanged.

All Claude calls mocked; pytest stays deterministic.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models import PromptLibrary


def _seed_library(db, entries: list[dict]) -> dict[str, str]:
    """Returns title -> library_id so tests can refer to seeded rows."""
    ids: dict[str, str] = {}
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
        db.refresh(row)
        ids[e["title"]] = row.library_id
    return ids


def _make_brief(client, auth_headers, *, client_name=None, prompt_type_picks=None,
                topic_states=None) -> str:
    payload = {"client_name": client_name} if client_name else {}
    resp = client.post("/briefs", json=payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    brief_id = resp.json()["brief_id"]

    step_answers = {}
    if prompt_type_picks:
        step_answers["topic_1_prompt_type"] = {
            "value": prompt_type_picks,
            "state": "green",
            "updated_at": "2026-04-28T00:00:00Z",
        }
    if topic_states:
        step_answers.update(topic_states)
    if step_answers:
        resp = client.patch(
            f"/briefs/{brief_id}",
            json={"step_answers": step_answers},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
    return brief_id


# ── library-matches ───────────────────────────────────────────────────────────

def test_matches_requires_auth(client, db):
    _seed_library(db, [{"title": "A", "prompt_type": "Extraction"}])
    resp = client.get("/briefs/some-id/library-matches")
    assert resp.status_code == 401


def test_matches_returns_empty_when_no_prompt_type_picked(client, auth_headers, db):
    _seed_library(db, [{"title": "Ext", "prompt_type": "Extraction"}])
    brief_id = _make_brief(client, auth_headers)
    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_matches_uses_prompt_type_from_topic_1_pick(client, auth_headers, db):
    _seed_library(db, [
        {"title": "Extraction entry", "prompt_type": "Extraction"},
        {"title": "Classification entry", "prompt_type": "Classification"},
    ])
    brief_id = _make_brief(client, auth_headers, prompt_type_picks=["Extraction"])
    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    titles = [m["title"] for m in resp.json()]
    assert titles == ["Extraction entry"]


def test_multiselect_prompt_type_prefers_extraction(client, auth_headers, db):
    """Multi-select rule: Extraction wins if present, else first picked."""
    _seed_library(db, [
        {"title": "Ext", "prompt_type": "Extraction"},
        {"title": "Cls", "prompt_type": "Classification"},
    ])
    brief_id = _make_brief(
        client, auth_headers, prompt_type_picks=["Classification", "Extraction"]
    )
    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    assert [m["title"] for m in resp.json()] == ["Ext"]


def test_matches_domain_signal_from_client_name(client, auth_headers, db):
    """client_name set → domain=finance bonus on finance entries."""
    _seed_library(db, [
        {
            "title": "Finance entry",
            "prompt_type": "Extraction",
            "domain": "finance",
        },
        {
            "title": "General entry",
            "prompt_type": "Extraction",
            "domain": "general",
        },
    ])
    brief_id = _make_brief(
        client, auth_headers, client_name="Lombard", prompt_type_picks=["Extraction"]
    )
    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    titles = [m["title"] for m in resp.json()]
    assert titles[0] == "Finance entry"


def test_matches_topic_signal_from_non_red_topics(client, auth_headers, db):
    _seed_library(db, [
        {
            "title": "Covers null+errors",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_8_null_handling", "topic_10_error_modes"],
        },
        {
            "title": "Covers nothing matching",
            "prompt_type": "Extraction",
            "topic_coverage": ["topic_9_confidence_traceability"],
        },
    ])
    brief_id = _make_brief(
        client, auth_headers,
        prompt_type_picks=["Extraction"],
        topic_states={
            "topic_8_null_handling": {"value": "skip", "state": "green",
                                      "updated_at": "2026-04-28T00:00:00Z"},
            "topic_10_error_modes": {"value": "fail loudly", "state": "amber",
                                     "updated_at": "2026-04-28T00:00:00Z"},
            # red entries shouldn't contribute to the topic signal
            "topic_6_data_points": {"value": "", "state": "red",
                                    "updated_at": "2026-04-28T00:00:00Z"},
        },
    )
    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    titles = [m["title"] for m in resp.json()]
    assert titles[0] == "Covers null+errors"


def test_matches_approved_flag_round_trips(client, auth_headers, db):
    """Approving a library_id via PATCH must surface as approved=True on
    the next library-matches call."""
    ids = _seed_library(db, [
        {"title": "Ext A", "prompt_type": "Extraction"},
        {"title": "Ext B", "prompt_type": "Extraction"},
    ])
    brief_id = _make_brief(client, auth_headers, prompt_type_picks=["Extraction"])

    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    assert resp.status_code == 200
    first_matches = resp.json()
    assert all(m["approved"] is False for m in first_matches)

    # Approve Ext A
    resp = client.patch(
        f"/briefs/{brief_id}",
        json={"approved_library_refs": [ids["Ext A"]]},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["approved_library_refs"] == [ids["Ext A"]]

    resp = client.get(f"/briefs/{brief_id}/library-matches", headers=auth_headers)
    by_title = {m["title"]: m for m in resp.json()}
    assert by_title["Ext A"]["approved"] is True
    assert by_title["Ext B"]["approved"] is False


def test_matches_404_for_missing_brief(client, auth_headers):
    resp = client.get(
        "/briefs/00000000-0000-0000-0000-000000000000/library-matches",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── library-references ────────────────────────────────────────────────────────

def test_references_empty_until_approval(client, auth_headers, db):
    _seed_library(db, [{
        "title": "Ext",
        "prompt_type": "Extraction",
        "full_text": "Extract fields. Name each field and source location.",
    }])
    brief_id = _make_brief(client, auth_headers, prompt_type_picks=["Extraction"])
    resp = client.get(f"/briefs/{brief_id}/library-references", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_references_with_topic_id_returns_excerpt_only_for_matching(client, auth_headers, db):
    ids = _seed_library(db, [
        {
            "title": "Has data-points text",
            "prompt_type": "Extraction",
            "full_text": "Extract fields. Name each field and its expected type.",
        },
        {
            "title": "No data-points text",
            "prompt_type": "Extraction",
            "full_text": "Write a poem about clouds.",
        },
    ])
    brief_id = _make_brief(client, auth_headers, prompt_type_picks=["Extraction"])
    client.patch(
        f"/briefs/{brief_id}",
        json={"approved_library_refs": [ids["Has data-points text"], ids["No data-points text"]]},
        headers=auth_headers,
    )
    resp = client.get(
        f"/briefs/{brief_id}/library-references?topic_id=topic_6_data_points",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()]
    # Only the entry whose text matches the topic survives the excerpt filter
    assert titles == ["Has data-points text"]
    payload = resp.json()[0]
    assert payload["library_id"] == ids["Has data-points text"]
    assert "field" in payload["excerpt"].lower()


def test_references_without_topic_id_returns_full_payload(client, auth_headers, db):
    ids = _seed_library(db, [{
        "title": "Ext",
        "prompt_type": "Extraction",
        "summary": "A short summary",
        "source_provenance": "Internal",
        "full_text": "The full prompt text.",
    }])
    brief_id = _make_brief(client, auth_headers, prompt_type_picks=["Extraction"])
    client.patch(
        f"/briefs/{brief_id}",
        json={"approved_library_refs": [ids["Ext"]]},
        headers=auth_headers,
    )
    resp = client.get(f"/briefs/{brief_id}/library-references", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "Ext"
    assert body[0]["full_text"] == "The full prompt text."
    assert body[0]["summary"] == "A short summary"


def test_references_404_for_missing_brief(client, auth_headers):
    resp = client.get(
        "/briefs/00000000-0000-0000-0000-000000000000/library-references",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── generation reference_examples wiring ─────────────────────────────────────

def _mock_claude_text(text: str) -> MagicMock:
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_response
    return mock_client


def test_generate_with_reference_examples_appends_block(client, auth_headers):
    mock_client = _mock_claude_text("Generated prompt body.")
    body = {
        "title": "Test",
        "prompt_type": "Extraction",
        "deployment_target": "Internal",
        "input_type": "Document",
        "output_type": "JSON",
        "brief_text": "Extract fields from a fund prospectus.",
        "constraints": [],
        "reference_examples": [
            {
                "title": "Reference A",
                "summary": "A short summary",
                "full_text": "Reference body alpha.",
            },
        ],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/prompts/generate", json=body, headers=auth_headers)

    assert resp.status_code == 200, resp.text
    sent_user = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "STRUCTURAL REFERENCE EXAMPLES" in sent_user
    assert "do not copy verbatim" in sent_user
    assert "Reference A" in sent_user
    assert "A short summary" in sent_user
    assert "Reference body alpha." in sent_user


def test_generate_without_reference_examples_omits_block(client, auth_headers):
    mock_client = _mock_claude_text("Generated prompt body.")
    body = {
        "title": "Test",
        "prompt_type": "Extraction",
        "deployment_target": "Internal",
        "input_type": "Document",
        "output_type": "JSON",
        "brief_text": "Extract fields from a fund prospectus.",
        "constraints": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/prompts/generate", json=body, headers=auth_headers)

    assert resp.status_code == 200, resp.text
    sent_user = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "STRUCTURAL REFERENCE EXAMPLES" not in sent_user
    assert "do not copy verbatim" not in sent_user


def test_generate_empty_reference_examples_omits_block(client, auth_headers):
    mock_client = _mock_claude_text("Generated prompt body.")
    body = {
        "title": "Test",
        "prompt_type": "Extraction",
        "deployment_target": "Internal",
        "input_type": "Document",
        "output_type": "JSON",
        "brief_text": "Extract fields from a fund prospectus.",
        "constraints": [],
        "reference_examples": [],
    }
    with patch("app.routers.generation.anthropic.Anthropic", return_value=mock_client):
        resp = client.post("/prompts/generate", json=body, headers=auth_headers)

    assert resp.status_code == 200
    sent_user = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "STRUCTURAL REFERENCE EXAMPLES" not in sent_user
