"""
Tests for the Operation lifecycle (Block 18).

Covers:
  - Auto-creation of operation_record when a deployment gate fires Approved.
  - Cadence resolves from form response, falling back to default.
  - Incident append; High/Critical flips state to Under Review.
  - Retire requires Checker; reason required.
  - Operation compliance run uses the same generic engine; bumps next_review.
  - Listing and filtering by state.
"""

import json

import pytest

from app.auth import hash_password
from app.models import OperationRecord, User
from services import operation_lifecycle


def _checker_login(client, db):
    """Get or create the standard ops-checker user. Idempotent so multiple
    deployments approved in one test reuse the same Checker session."""
    email = "ops-checker@test.local"
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        existing = User(
            email=email,
            name="Ops Checker",
            role="Checker",
            password_hash=hash_password("checkerpass"),
            is_active=True,
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)
    resp = client.post(
        "/auth/login",
        data={"username": email, "password": "checkerpass"},
    )
    return existing, {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch, cadence="120"):
    """End-to-end fixture helper: prompt → deployment → submit → run
    compliance with all 5s → checker approves. Returns operation_id."""
    payload = {
        "title": "Op test",
        "prompt_type": "Analysis",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 180,
        "prompt_text": "Op text.",
        "change_summary": "v1",
    }
    p = client.post("/prompts", json=payload, headers=auth_headers).json()
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
        "change_review_frequency_days": cadence,
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
        return json.dumps({"scores": {c: {"score": 5, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr("services.compliance_engine._call_claude", fake_call)
    client.post(f"/deployments/{deployment_id}/compliance", headers=auth_headers)

    _checker, checker_headers = _checker_login(client, db)
    decision = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    assert decision.status_code == 201, decision.text

    op = (
        db.query(OperationRecord)
        .filter(OperationRecord.deployment_id == deployment_id)
        .one_or_none()
    )
    assert op is not None
    return op.operation_id, checker_headers


# ── Auto-creation ──────────────────────────────────────────────────────────

def test_operation_record_auto_created_on_approval(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    db.expire_all()
    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    assert rec is not None
    assert rec.state == "Active"
    assert rec.review_cadence_days == 120  # from the form response above
    assert rec.next_review_date is not None


def test_cadence_falls_back_to_default(client, auth_headers, test_user, db, monkeypatch):
    """A deployment whose form response gives a non-numeric cadence
    falls back to the global default (90)."""
    payload = {
        "title": "Cadence fallback",
        "prompt_type": "Analysis",
        "deployment_target": "O", "input_type": "Plain text",
        "output_type": "Plain text", "risk_tier": "Limited",
        "review_cadence_days": 90, "prompt_text": "x", "change_summary": "v1",
    }
    p = client.post("/prompts", json=payload, headers=auth_headers).json()
    create = client.post(
        "/deployments",
        json={"prompt_id": p["prompt_id"], "version_id": p["versions"][0]["version_id"]},
        headers=auth_headers,
    )
    deployment_id = create.json()["deployment_id"]

    # Stash an empty cadence response by saving with PATCH-like helper
    from app.models import DeploymentRecord
    rec = db.query(DeploymentRecord).filter(DeploymentRecord.deployment_id == deployment_id).first()
    rec.form_responses_json = json.dumps({})
    db.commit()
    cadence = operation_lifecycle.resolve_cadence_days(db, rec)
    assert cadence == 90


# ── Incidents ──────────────────────────────────────────────────────────────

def test_incident_low_does_not_change_state(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.post(
        f"/operation/{operation_id}/incidents",
        json={"severity": "Low", "category": "Quality", "summary": "Minor."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["record"]["state"] == "Active"


def test_incident_high_flips_to_under_review(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.post(
        f"/operation/{operation_id}/incidents",
        json={"severity": "High", "category": "Security", "summary": "Suspected leak."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["record"]["state"] == "Under Review"


def test_incident_invalid_severity(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.post(
        f"/operation/{operation_id}/incidents",
        json={"severity": "Catastrophic", "category": "Other", "summary": "x"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


# ── Retire / return-to-active ─────────────────────────────────────────────

def test_retire_requires_checker(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    # Maker
    resp = client.post(
        f"/operation/{operation_id}/retire",
        json={"reason": "Outdated"},
        headers=auth_headers,
    )
    assert resp.status_code == 403


def test_retire_checker(client, auth_headers, test_user, db, monkeypatch):
    operation_id, checker_headers = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.post(
        f"/operation/{operation_id}/retire",
        json={"reason": "Replaced by v2 prompt"},
        headers=checker_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "Retired"
    assert body["retired_reason"] == "Replaced by v2 prompt"


def test_retire_requires_reason(client, auth_headers, test_user, db, monkeypatch):
    operation_id, checker_headers = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    resp = client.post(
        f"/operation/{operation_id}/retire",
        json={},
        headers=checker_headers,
    )
    assert resp.status_code == 422


def test_return_to_active(client, auth_headers, test_user, db, monkeypatch):
    operation_id, checker_headers = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    # Trigger High incident → Under Review
    client.post(
        f"/operation/{operation_id}/incidents",
        json={"severity": "High", "category": "Quality", "summary": "Spike"},
        headers=auth_headers,
    )
    resp = client.post(
        f"/operation/{operation_id}/return-to-active",
        headers=checker_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "Active"


# ── Compliance run ─────────────────────────────────────────────────────────

def test_run_operation_compliance(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)

    def fake_call(system_prompt, _user_message):
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": 5, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr("services.compliance_engine._call_claude", fake_call)
    resp = client.post(f"/operation/{operation_id}/run", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["overall_result"] in ("Pass", "Pass with warnings")
    # Each scored dimension carries the standards label
    for s in body["scores"]:
        assert s.get("standard", {}).get("standard_code")


def test_failed_run_flips_to_under_review(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)

    def fake_call(system_prompt, _user_message):
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": 1, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr("services.compliance_engine._call_claude", fake_call)
    client.post(f"/operation/{operation_id}/run", headers=auth_headers)
    resp = client.get(f"/operation/{operation_id}", headers=auth_headers)
    assert resp.json()["state"] == "Under Review"


# ── Listing ────────────────────────────────────────────────────────────────

def test_list_filters_by_state(client, auth_headers, test_user, db, monkeypatch):
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    # Create a second one and retire it
    op2_id, checker_headers = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    client.post(
        f"/operation/{op2_id}/retire",
        json={"reason": "Replaced"},
        headers=checker_headers,
    )

    active = client.get("/operation?state=Active", headers=auth_headers).json()
    retired = client.get("/operation?state=Retired", headers=auth_headers).json()
    active_ids = {r["operation_id"] for r in active}
    retired_ids = {r["operation_id"] for r in retired}
    assert operation_id in active_ids
    assert op2_id in retired_ids


# ── Idempotency ────────────────────────────────────────────────────────────

def test_double_approval_does_not_create_second_record(client, auth_headers, test_user, db, monkeypatch):
    """If the gate were called twice (unlikely after Block 16's 409), the
    operation_record creation is idempotent and returns the same row."""
    operation_id, _ = _approve_one_deployment(client, auth_headers, test_user, db, monkeypatch)
    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    duplicate = operation_lifecycle.create_operation_record_for_deployment(
        db,
        db.query(__import__("app.models", fromlist=["DeploymentRecord"]).DeploymentRecord)
        .filter_by(deployment_id=rec.deployment_id).one(),
    )
    assert duplicate.operation_id == operation_id
