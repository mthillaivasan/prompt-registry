"""Tests for prompt and version endpoints — Session 4.5."""

import pytest

from app.models import AuditLog, Prompt, PromptVersion


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_payload(**overrides):
    payload = {
        "title": "Customer summary",
        "prompt_type": "Summarisation",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 180,
        "prompt_text": "Summarise the following customer email in three bullets.",
        "change_summary": "Initial version",
    }
    payload.update(overrides)
    return payload


def _create_prompt(client, headers, **overrides):
    return client.post("/prompts", json=_create_payload(**overrides), headers=headers)


# ── Auth tests ───────────────────────────────────────────────────────────────

def test_create_prompt_requires_auth(client):
    resp = client.post("/prompts", json=_create_payload())
    assert resp.status_code == 401


def test_list_prompts_requires_auth(client):
    resp = client.get("/prompts")
    assert resp.status_code == 401


def test_invalid_token_is_rejected(client):
    resp = client.get("/prompts", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


# ── Create prompt ────────────────────────────────────────────────────────────

def test_create_prompt_returns_201_and_full_detail(client, auth_headers):
    resp = _create_prompt(client, auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Customer summary"
    assert body["status"] == "Draft"
    assert body["prompt_type"] == "Summarisation"
    assert body["risk_tier"] == "Limited"
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version_number"] == 1
    assert body["versions"][0]["is_active"] is False
    assert body["active_version"] is None


def test_create_prompt_sets_owner_to_current_user(client, auth_headers, test_user):
    resp = _create_prompt(client, auth_headers)
    assert resp.json()["owner_id"] == test_user.user_id


def test_create_prompt_writes_audit_log(client, auth_headers, db):
    resp = _create_prompt(client, auth_headers)
    prompt_id = resp.json()["prompt_id"]
    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == prompt_id, AuditLog.action == "Created")
        .first()
    )
    assert log is not None
    assert log.entity_type == "Prompt"


def test_create_prompt_rejects_invalid_prompt_type(client, auth_headers):
    resp = _create_prompt(client, auth_headers, prompt_type="NotAType")
    assert resp.status_code == 422


def test_create_prompt_rejects_invalid_risk_tier(client, auth_headers):
    resp = _create_prompt(client, auth_headers, risk_tier="VeryHigh")
    assert resp.status_code == 422


def test_create_prompt_requires_prompt_text(client, auth_headers):
    payload = _create_payload()
    payload["prompt_text"] = ""
    resp = client.post("/prompts", json=payload, headers=auth_headers)
    assert resp.status_code == 422


def test_create_prompt_populates_token_count_and_cost(client, auth_headers, db):
    """Drop 1: new v1 row must carry token_count + estimated_cost_usd."""
    resp = _create_prompt(client, auth_headers)
    assert resp.status_code == 201, resp.text
    v1 = resp.json()["versions"][0]
    assert v1["token_count"] is not None
    assert v1["token_count"] > 0
    assert v1["estimated_cost_usd"] is not None
    # Stored as decimal-safe string (e.g. "0.0075")
    cost = float(v1["estimated_cost_usd"])
    assert cost > 0


# ── List & get prompts ───────────────────────────────────────────────────────

def test_list_prompts_returns_only_user_visible(client, auth_headers):
    _create_prompt(client, auth_headers, title="A")
    _create_prompt(client, auth_headers, title="B")
    resp = client.get("/prompts", headers=auth_headers)
    assert resp.status_code == 200
    titles = {p["title"] for p in resp.json()}
    assert {"A", "B"}.issubset(titles)


def test_list_prompts_filters_by_status(client, auth_headers):
    _create_prompt(client, auth_headers, title="Draft1")
    resp = client.get("/prompts?status=Active", headers=auth_headers)
    assert resp.status_code == 200
    assert all(p["status"] == "Active" for p in resp.json())


def test_list_prompts_filters_by_risk_tier(client, auth_headers):
    _create_prompt(client, auth_headers, title="Limited", risk_tier="Limited")
    _create_prompt(client, auth_headers, title="High", risk_tier="High")
    resp = client.get("/prompts?risk_tier=High", headers=auth_headers)
    titles = [p["title"] for p in resp.json()]
    assert "High" in titles
    assert "Limited" not in titles


def test_list_prompts_searches_title(client, auth_headers):
    _create_prompt(client, auth_headers, title="Loan summariser")
    _create_prompt(client, auth_headers, title="Risk classifier")
    resp = client.get("/prompts?search=loan", headers=auth_headers)
    titles = [p["title"] for p in resp.json()]
    assert titles == ["Loan summariser"]


def test_get_prompt_returns_versions(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.get(f"/prompts/{prompt_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["versions"]) == 1


def test_get_prompt_404_for_unknown_id(client, auth_headers):
    resp = client.get("/prompts/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


# ── Update prompt ────────────────────────────────────────────────────────────

def test_patch_title(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.patch(
        f"/prompts/{prompt_id}",
        json={"title": "Renamed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed"


def test_patch_status_invalid_transition_returns_409(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    # Draft → Review Required is not in _TRANSITIONS["Draft"]
    resp = client.patch(
        f"/prompts/{prompt_id}",
        json={"status": "Review Required"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_patch_status_to_retired(client, auth_headers, db):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.patch(
        f"/prompts/{prompt_id}",
        json={"status": "Retired"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "Retired"
    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == prompt_id, AuditLog.action == "Retired")
        .first()
    )
    assert log is not None


def test_patch_unknown_approver_returns_400(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.patch(
        f"/prompts/{prompt_id}",
        json={"approver_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_patch_existing_approver_succeeds(client, auth_headers, second_user):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.patch(
        f"/prompts/{prompt_id}",
        json={"approver_id": second_user.user_id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["approver_id"] == second_user.user_id


def test_patch_with_no_changes_is_noop(client, auth_headers, db):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    initial_audit = db.query(AuditLog).count()
    resp = client.patch(f"/prompts/{prompt_id}", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert db.query(AuditLog).count() == initial_audit  # no Edited entry


# ── Versions ────────────────────────────────────────────────────────────────

def test_create_version_increments_number(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.post(
        f"/prompts/{prompt_id}/versions",
        json={"prompt_text": "Updated content", "change_summary": "Tightened wording"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["version_number"] == 2
    assert resp.json()["previous_version_id"] is not None


def test_create_version_writes_audit(client, auth_headers, db):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.post(
        f"/prompts/{prompt_id}/versions",
        json={"prompt_text": "v2"},
        headers=auth_headers,
    )
    version_id = resp.json()["version_id"]
    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == version_id, AuditLog.action == "Edited")
        .first()
    )
    assert log is not None


def test_create_version_on_retired_prompt_returns_409(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    client.patch(f"/prompts/{prompt_id}", json={"status": "Retired"}, headers=auth_headers)
    resp = client.post(
        f"/prompts/{prompt_id}/versions",
        json={"prompt_text": "should fail"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_list_versions_orders_desc(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    client.post(f"/prompts/{prompt_id}/versions", json={"prompt_text": "v2"}, headers=auth_headers)
    client.post(f"/prompts/{prompt_id}/versions", json={"prompt_text": "v3"}, headers=auth_headers)
    resp = client.get(f"/prompts/{prompt_id}/versions", headers=auth_headers)
    assert resp.status_code == 200
    nums = [v["version_number"] for v in resp.json()]
    assert nums == [3, 2, 1]


def test_get_version_returns_404_for_wrong_id(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.get(
        f"/prompts/{prompt_id}/versions/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── Activation ──────────────────────────────────────────────────────────────

def test_activate_version_marks_active_and_promotes_prompt(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    version_id = create_resp.json()["versions"][0]["version_id"]

    resp = client.post(
        f"/prompts/{prompt_id}/versions/{version_id}/activate",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is True
    assert resp.json()["approved_by"] is not None
    assert resp.json()["approved_at"] is not None

    # Prompt status should have moved Draft → Active
    p = client.get(f"/prompts/{prompt_id}", headers=auth_headers).json()
    assert p["status"] == "Active"
    assert p["active_version"]["version_id"] == version_id


def test_activating_new_version_deactivates_previous(client, auth_headers, db):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    v1_id = create_resp.json()["versions"][0]["version_id"]

    client.post(f"/prompts/{prompt_id}/versions/{v1_id}/activate", headers=auth_headers)

    v2 = client.post(
        f"/prompts/{prompt_id}/versions",
        json={"prompt_text": "v2"},
        headers=auth_headers,
    ).json()
    client.post(f"/prompts/{prompt_id}/versions/{v2['version_id']}/activate", headers=auth_headers)

    actives = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id, PromptVersion.is_active == True)  # noqa: E712
        .all()
    )
    assert len(actives) == 1
    assert actives[0].version_id == v2["version_id"]


def test_activate_writes_approved_audit(client, auth_headers, db):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    version_id = create_resp.json()["versions"][0]["version_id"]
    client.post(f"/prompts/{prompt_id}/versions/{version_id}/activate", headers=auth_headers)
    log = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == version_id, AuditLog.action == "Approved")
        .first()
    )
    assert log is not None


def test_activate_version_404_for_unknown_id(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    resp = client.post(
        f"/prompts/{prompt_id}/versions/00000000-0000-0000-0000-000000000000/activate",
        headers=auth_headers,
    )
    assert resp.status_code == 404


def test_activate_on_retired_prompt_returns_409(client, auth_headers):
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    version_id = create_resp.json()["versions"][0]["version_id"]
    client.patch(f"/prompts/{prompt_id}", json={"status": "Retired"}, headers=auth_headers)
    resp = client.post(
        f"/prompts/{prompt_id}/versions/{version_id}/activate",
        headers=auth_headers,
    )
    assert resp.status_code == 409


# ── Immutability sanity ─────────────────────────────────────────────────────

def test_prompt_version_text_cannot_be_changed_at_db_level(client, auth_headers, db):
    """The DB trigger must reject any attempt to alter prompt_text."""
    create_resp = _create_prompt(client, auth_headers)
    prompt_id = create_resp.json()["prompt_id"]
    version = (
        db.query(PromptVersion).filter(PromptVersion.prompt_id == prompt_id).first()
    )
    version.prompt_text = "tampered"
    with pytest.raises(Exception):
        db.commit()
    db.rollback()
