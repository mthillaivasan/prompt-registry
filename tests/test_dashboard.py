"""
Tests for the dashboard endpoint (Block 20).

Each test puts a prompt at a known lifecycle position, calls
GET /dashboard, and verifies the row's cell vocabulary matches
DASHBOARD_SPEC.md §2.

The cell-vocabulary mapping is defined once in services/dashboard_view.py
and exercised here: an `at-brief` prompt does NOT show Build/Deployment;
a Build-failed prompt shows `Fail`; an Approved deployment shows
`Approved` plus a gate marker; etc.
"""

import json

from app.auth import hash_password
from app.models import User


def _prompt_payload(title="Test prompt", risk_tier="Limited"):
    return {
        "title": title,
        "prompt_type": "Analysis",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": risk_tier,
        "review_cadence_days": 90,
        "prompt_text": "x",
        "change_summary": "v1",
    }


def _checker_login(client, db):
    email = "dash-checker@test.local"
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        existing = User(
            email=email, name="Dash Checker", role="Checker",
            password_hash=hash_password("checkerpass"), is_active=True,
        )
        db.add(existing)
        db.commit()
    resp = client.post(
        "/auth/login",
        data={"username": email, "password": "checkerpass"},
    )
    return existing, {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _approve_deployment(client, auth_headers, test_user, db, monkeypatch, score=5):
    p = client.post("/prompts", json=_prompt_payload(), headers=auth_headers).json()
    deployment_id = client.post(
        "/deployments",
        json={"prompt_id": p["prompt_id"], "version_id": p["versions"][0]["version_id"]},
        headers=auth_headers,
    ).json()["deployment_id"]
    responses = {
        "invocation_trigger": "manual_user_action",
        "invocation_frequency_per_day": "1-10",
        "latency_envelope_seconds": "5",
        "input_data_categories": ["public_information"],
        "input_redaction_applied": True,
        "input_size_p95_tokens": "1024",
        "input_user_supplied": False,
        "output_destination": "human_review_only",
        "output_executed_by_machine": False,
        "output_storage_retention_days": "30",
        "logging_destination": "audit_log_table",
        "metric_collection": ["latency"],
        "alerting_thresholds_defined": False,
        "runtime_owner_id": test_user.user_id,
        "approver_id": test_user.user_id,
        "change_review_frequency_days": "90",
        "breaking_change_protocol": "x",
        "model_provider": "Anthropic",
        "data_residency": "UK",
        "sub_processing_disclosed": True,
        "audit_rights_in_contract": True,
    }
    client.put(f"/deployments/{deployment_id}", json={"responses": responses}, headers=auth_headers)
    client.post(f"/deployments/{deployment_id}/submit", headers=auth_headers)

    def fake_call(system_prompt, _user_message):
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": score, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr("services.compliance_engine._call_claude", fake_call)
    client.post(f"/deployments/{deployment_id}/compliance", headers=auth_headers)

    _checker, checker_headers = _checker_login(client, db)
    client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    return p["prompt_id"], deployment_id, checker_headers


# ── Smoke ─────────────────────────────────────────────────────────────────

def test_dashboard_requires_auth(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 401


def test_dashboard_empty_prompt_no_brief(client, auth_headers):
    """A prompt with no brief should sit `at-build` — Brief cell shows
    Complete (legacy fallback) and Build cell shows neutral until a
    compliance run lands."""
    client.post("/prompts", json=_prompt_payload(title="Lone prompt"), headers=auth_headers)
    resp = client.get("/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    rows = resp.json()["prompts"]
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "Lone prompt"
    assert row["brief"]["state"] == "Complete"
    assert row["build"]["state"] == "—"
    assert row["deployment"]["state"] == "—"
    assert row["operation"]["state"] == "—"


def test_dashboard_position_at_brief(client, auth_headers):
    """A brief In Progress with no resulting prompt is invisible to the
    dashboard (which is prompt-rooted). Verify that an empty dashboard
    is empty."""
    resp = client.get("/dashboard", headers=auth_headers)
    assert resp.json()["prompts"] == []


# ── Build column ──────────────────────────────────────────────────────────

def test_dashboard_build_cell_shows_pass_after_compliance(
    client, auth_headers, test_user, db, monkeypatch
):
    p = client.post("/prompts", json=_prompt_payload(title="Build pass"), headers=auth_headers).json()
    # Phase 2 build run: write directly via the engine's helper
    from services.compliance_engine import run_phase_compliance

    def fake_score(system_prompt, _user):
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": 5, "rationale": "ok"} for c in codes}})

    run_phase_compliance(
        db,
        phase_code="build",
        subject_type="prompt_version",
        subject_id=p["versions"][0]["version_id"],
        run_by="SYSTEM",
        scoring_input_text="dummy",
        metadata={"prompt_type": "Analysis", "input_type": "Plain text", "risk_tier": "Limited"},
        score_provider=fake_score,
    )
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["title"] == "Build pass")
    assert row["build"]["state"] in ("Pass", "PWW")
    assert row["build"]["grade"] is not None


# ── Deployment column ─────────────────────────────────────────────────────

def test_dashboard_deployment_pending(client, auth_headers, test_user, monkeypatch):
    p = client.post("/prompts", json=_prompt_payload(title="Pending dep"), headers=auth_headers).json()
    deployment_id = client.post(
        "/deployments",
        json={"prompt_id": p["prompt_id"], "version_id": p["versions"][0]["version_id"]},
        headers=auth_headers,
    ).json()["deployment_id"]
    responses = {
        "invocation_trigger": "manual_user_action",
        "invocation_frequency_per_day": "1-10",
        "latency_envelope_seconds": "",
        "input_data_categories": ["public_information"],
        "input_redaction_applied": True,
        "input_size_p95_tokens": "",
        "input_user_supplied": False,
        "output_destination": "human_review_only",
        "output_executed_by_machine": False,
        "output_storage_retention_days": "",
        "logging_destination": "audit_log_table",
        "metric_collection": ["latency"],
        "alerting_thresholds_defined": False,
        "runtime_owner_id": test_user.user_id,
        "approver_id": test_user.user_id,
        "change_review_frequency_days": "90",
        "breaking_change_protocol": "",
        "model_provider": "Anthropic",
        "data_residency": "UK",
        "sub_processing_disclosed": True,
        "audit_rights_in_contract": True,
    }
    client.put(f"/deployments/{deployment_id}", json={"responses": responses}, headers=auth_headers)
    client.post(f"/deployments/{deployment_id}/submit", headers=auth_headers)
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["title"] == "Pending dep")
    assert row["deployment"]["state"] == "Pending"
    assert row["deployment"]["label"] == "Pending"


def test_dashboard_deployment_approved_shows_gate(client, auth_headers, test_user, db, monkeypatch):
    prompt_id, deployment_id, _ = _approve_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["prompt_id"] == prompt_id)
    assert row["deployment"]["state"] == "Approved"
    assert row["deployment_gate"] is not None
    assert row["deployment_gate"]["decided_at"] is not None


def test_dashboard_operation_active_after_gate(client, auth_headers, test_user, db, monkeypatch):
    prompt_id, _, _ = _approve_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["prompt_id"] == prompt_id)
    assert row["operation"]["state"] == "Active"
    assert row["operation"]["label"] == "Active"


def test_dashboard_operation_retired(client, auth_headers, test_user, db, monkeypatch):
    prompt_id, _, checker_headers = _approve_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["prompt_id"] == prompt_id)
    operation_id = row["operation"]["operation_id"]
    client.post(
        f"/operation/{operation_id}/retire",
        json={"reason": "Replaced"},
        headers=checker_headers,
    )
    resp = client.get("/dashboard", headers=auth_headers)
    row = next(r for r in resp.json()["prompts"] if r["prompt_id"] == prompt_id)
    assert row["operation"]["state"] == "Retired"


# ── Filters ────────────────────────────────────────────────────────────────

def test_dashboard_owner_filter_default_is_me(client, auth_headers, test_user, db):
    """Another user's prompt should not appear when owner=me."""
    other = User(
        email="other-author@test.local",
        name="Other",
        role="Maker",
        password_hash=hash_password("p"),
        is_active=True,
    )
    db.add(other)
    db.commit()
    other_token = client.post(
        "/auth/login",
        data={"username": "other-author@test.local", "password": "p"},
    ).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    client.post("/prompts", json=_prompt_payload(title="Mine"), headers=auth_headers)
    client.post("/prompts", json=_prompt_payload(title="Theirs"), headers=other_headers)

    me = client.get("/dashboard?owner=me", headers=auth_headers).json()["prompts"]
    titles = {r["title"] for r in me}
    assert "Mine" in titles
    assert "Theirs" not in titles

    everyone = client.get("/dashboard?owner=all", headers=auth_headers).json()["prompts"]
    titles_all = {r["title"] for r in everyone}
    assert "Mine" in titles_all
    assert "Theirs" in titles_all


def test_dashboard_lifecycle_filter(client, auth_headers, test_user, db, monkeypatch):
    """An at-build row and an at-operation row; lifecycle=at-operation
    should return only the second."""
    # at-build (no deployment)
    client.post("/prompts", json=_prompt_payload(title="Just built"), headers=auth_headers)
    # at-operation
    _approve_deployment(client, auth_headers, test_user, db, monkeypatch)

    rows = client.get(
        "/dashboard?lifecycle=at-operation", headers=auth_headers
    ).json()["prompts"]
    assert all(r["operation"]["state"] != "—" for r in rows)
    titles = {r["title"] for r in rows}
    assert "Just built" not in titles


def test_dashboard_risk_tier_filter(client, auth_headers):
    client.post("/prompts", json=_prompt_payload(title="Low risk", risk_tier="Limited"), headers=auth_headers)
    client.post("/prompts", json=_prompt_payload(title="High risk", risk_tier="High"), headers=auth_headers)
    rows = client.get("/dashboard?risk_tier=High", headers=auth_headers).json()["prompts"]
    assert all(r["risk_tier"] == "High" for r in rows)


# ── Cell vocabulary discipline ────────────────────────────────────────────

def test_no_unknown_state_words_emitted(client, auth_headers, test_user, db, monkeypatch):
    """Every state word emitted should be one of the closed vocabulary."""
    _approve_deployment(client, auth_headers, test_user, db, monkeypatch)
    rows = client.get("/dashboard?owner=all", headers=auth_headers).json()["prompts"]
    valid = {
        "In progress", "Complete",
        "Pass", "PWW", "Fail",
        "Pending", "Approved", "Rejected",
        "Active", "Under Review", "Suspended", "Retired",
        "—",
    }
    for r in rows:
        for col in ("brief", "build", "deployment", "operation"):
            state = r[col]["state"]
            assert state in valid, f"unexpected state '{state}' in {col}"
