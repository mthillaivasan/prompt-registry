"""
Tests for the Deployment gate (Block 16).

Covers:
  - Gate role enforcement reads from gates config (Maker rejected, Checker accepted).
  - Rationale required enforcement reads from gates config.
  - Cannot approve a deployment whose compliance run is Fail.
  - Approved/Rejected transitions the DeploymentRecord status.
  - GateDecision row is written; audit log entry recorded.
"""

import json

from app.models import AuditLog, GateDecision, User
from app.auth import hash_password


def _bootstrap_deployment(client, headers, test_user_id, monkeypatch, score_value=5):
    """Create prompt → deployment → submit → run compliance.

    Returns deployment_id with the record sitting in Pending Approval and
    a compliance run on file. `score_value` lets the caller produce a
    Pass (5) or Fail (1) latest run.
    """
    payload = {
        "title": "Gate test prompt",
        "prompt_type": "Analysis",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 180,
        "prompt_text": "Analyse the input.",
        "change_summary": "v1",
    }
    p = client.post("/prompts", json=payload, headers=headers).json()
    prompt_id = p["prompt_id"]
    version_id = p["versions"][0]["version_id"]

    create = client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=headers,
    )
    deployment_id = create.json()["deployment_id"]

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
        "runtime_owner_id": test_user_id,
        "approver_id": test_user_id,
        "change_review_frequency_days": "90",
        "breaking_change_protocol": "Change-management mailbox.",
        "model_provider": "Anthropic",
        "data_residency": "UK",
        "sub_processing_disclosed": True,
        "audit_rights_in_contract": True,
    }
    client.put(
        f"/deployments/{deployment_id}",
        json={"responses": responses},
        headers=headers,
    )
    client.post(f"/deployments/{deployment_id}/submit", headers=headers)

    def fake_call(system_prompt, _user_message):
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": score_value, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr("services.compliance_engine._call_claude", fake_call)
    resp = client.post(f"/deployments/{deployment_id}/compliance", headers=headers)
    assert resp.status_code == 201, resp.text
    return deployment_id


def _checker_login(client, db):
    user = User(
        email="checker@test.local",
        name="Test Checker",
        role="Checker",
        password_hash=hash_password("checkerpass"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    resp = client.post(
        "/auth/login",
        data={"username": "checker@test.local", "password": "checkerpass"},
    )
    return user, {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Decision endpoint ──────────────────────────────────────────────────────

def test_gate_blocks_when_no_compliance_run(client, auth_headers, test_user, db):
    """No /compliance run means 409 from the gate."""
    payload = {
        "title": "x", "prompt_type": "Analysis", "deployment_target": "O",
        "input_type": "Plain text", "output_type": "Plain text",
        "risk_tier": "Limited", "review_cadence_days": 90,
        "prompt_text": "x", "change_summary": "v1",
    }
    p = client.post("/prompts", json=payload, headers=auth_headers).json()
    create = client.post(
        "/deployments",
        json={"prompt_id": p["prompt_id"], "version_id": p["versions"][0]["version_id"]},
        headers=auth_headers,
    )
    deployment_id = create.json()["deployment_id"]
    # Get the form responses then submit, but don't run compliance.
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

    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "Looks fine"},
        headers=checker_headers,
    )
    assert resp.status_code == 409
    assert "compliance run" in resp.json()["detail"].lower()


def test_gate_rejects_maker_role(client, auth_headers, test_user, db, monkeypatch):
    """Gate config says approver_role=Checker; a Maker is forbidden."""
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    # test_user is a Maker
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "fine"},
        headers=auth_headers,
    )
    assert resp.status_code == 403
    assert "role" in resp.json()["detail"].lower()


def test_gate_accepts_checker_role(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "Reviewed runtime config; sign-off."},
        headers=checker_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decision"] == "Approved"
    assert body["deployment_status"] == "Approved"


def test_gate_rationale_required(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved"},
        headers=checker_headers,
    )
    assert resp.status_code == 422
    assert "rationale" in resp.json()["detail"].lower()


def test_gate_rejection_path(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Rejected", "rationale": "Output handling unclear; revise."},
        headers=checker_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decision"] == "Rejected"
    assert body["deployment_status"] == "Rejected"


def test_gate_blocks_approval_on_failed_compliance(client, auth_headers, test_user, db, monkeypatch):
    """A compliance run with overall Fail must block approval."""
    deployment_id = _bootstrap_deployment(
        client, auth_headers, test_user.user_id, monkeypatch, score_value=1
    )
    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "still want to push it"},
        headers=checker_headers,
    )
    assert resp.status_code == 409
    assert "fail" in resp.json()["detail"].lower()


def test_gate_writes_decision_row_and_audit(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "Reviewed and accepted."},
        headers=checker_headers,
    )
    assert resp.status_code == 201
    decision_id = resp.json()["decision_id"]

    db.expire_all()
    decision = db.query(GateDecision).filter(GateDecision.decision_id == decision_id).first()
    assert decision is not None
    assert decision.decided_by == checker_user.user_id
    assert decision.subject_id == deployment_id
    assert decision.subject_type == "deployment_record"

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == deployment_id, AuditLog.action == "Approved")
        .all()
    )
    assert len(audits) >= 1


def test_gate_decisions_listing(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    resp = client.get(
        f"/deployments/{deployment_id}/gate-decisions",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) >= 1
    assert body[0]["decision"] == "Approved"
    assert body[0]["rationale"] == "ok"


def test_gate_invalid_decision_value(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Maybe", "rationale": "..."},
        headers=checker_headers,
    )
    assert resp.status_code == 422


def test_gate_rejects_when_record_not_pending(client, auth_headers, test_user, db, monkeypatch):
    deployment_id = _bootstrap_deployment(client, auth_headers, test_user.user_id, monkeypatch)
    _checker_user, checker_headers = _checker_login(client, db)
    # First approval moves status to Approved; second call should 409.
    client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    resp = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "again"},
        headers=checker_headers,
    )
    assert resp.status_code == 409
