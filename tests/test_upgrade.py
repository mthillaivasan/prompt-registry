"""Tests for import and upgrade pipeline — Session 4."""

import json
from unittest.mock import patch

from app.models import AuditLog, PromptVersion, UpgradeProposal


# ── Mock responses ───────────────────────────────────────────────────────────

MOCK_ANALYSIS = json.dumps({
    "classification": {
        "inferred_purpose": "Customer service chatbot",
        "prompt_type": "Comms",
        "deployment_target": "Internal",
        "risk_tier": "Limited",
        "confidence": "High",
    },
    "findings": [
        {
            "finding_id": "f-001",
            "dimension_code": "REG_D1",
            "dimension_name": "Human Oversight",
            "framework": "REGULATORY",
            "current_score": 1,
            "current_finding": "No human review step declared.",
            "severity": "Blocking",
            "source_reference": "EU AI Act Article 14",
        },
        {
            "finding_id": "f-002",
            "dimension_code": "REG_D2",
            "dimension_name": "Transparency",
            "framework": "REGULATORY",
            "current_score": 2,
            "current_finding": "Not declared AI-generated.",
            "severity": "Blocking",
            "source_reference": "EU AI Act Article 13",
        },
    ],
    "suggestions": [
        {
            "suggestion_id": "s-001",
            "finding_id": "f-001",
            "dimension_code": "REG_D1",
            "change_type": "Addition",
            "description": "Add human review.",
            "suggested_text": "A qualified reviewer must approve this output.",
            "rationale": "EU AI Act Art 14",
            "expected_score_improvement": {"from": 1, "to": 5},
            "insertion_hint": "End",
        },
        {
            "suggestion_id": "s-002",
            "finding_id": "f-002",
            "dimension_code": "REG_D2",
            "change_type": "Addition",
            "description": "Declare AI-generated.",
            "suggested_text": "This output is AI-generated and advisory only.",
            "rationale": "EU AI Act Art 13",
            "expected_score_improvement": {"from": 2, "to": 5},
            "insertion_hint": "Start",
        },
    ],
})

MOCK_VALIDATION_CLEAN = json.dumps({
    "result": "clean",
    "confidence": 0.92,
    "reason": "Output follows expected structure",
})

MOCK_INJECTION_CLEAN = json.dumps({
    "result": "clean",
    "confidence": 0.95,
    "reason": "No injection detected",
})

SAMPLE_PROMPT = "You are a helpful customer service agent. Answer questions."


def _mock_call_claude(system_prompt, user_message):
    if "Analyse this prompt" in user_message:
        return MOCK_ANALYSIS
    if "Output to review" in user_message:
        return MOCK_VALIDATION_CLEAN
    return MOCK_INJECTION_CLEAN


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_prompt(client, headers):
    return client.post("/prompts", json={
        "title": "Upgrade test",
        "prompt_type": "Comms",
        "deployment_target": "Internal",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "prompt_text": SAMPLE_PROMPT,
    }, headers=headers)


def _analyse(client, headers, prompt_text=SAMPLE_PROMPT, **extra):
    body = {"prompt_text": prompt_text, **extra}
    with patch("services.upgrade_engine._call_claude", side_effect=_mock_call_claude):
        return client.post("/prompts/analyse", json=body, headers=headers)


def _respond(client, headers, proposal_id, suggestion_id, response, **extra):
    return client.post(
        f"/proposals/{proposal_id}/responses",
        json={"suggestion_id": suggestion_id, "response": response, **extra},
        headers=headers,
    )


# ── Tests: POST /prompts/analyse ─────────────────────────────────────────────

def test_analyse_requires_auth(client):
    resp = client.post("/prompts/analyse", json={"prompt_text": "test"})
    assert resp.status_code == 401


def test_analyse_returns_proposal_and_job(client, auth_headers):
    resp = _analyse(client, auth_headers)
    assert resp.status_code == 202
    data = resp.json()
    assert "proposal_id" in data
    assert "job_id" in data
    assert data["status"] == "Queued"


def test_analyse_creates_audit_log(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    log = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "PromptImported",
    ).first()
    assert log is not None


def test_analyse_writes_upgrade_proposed_audit(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    log = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "UpgradeProposed",
    ).first()
    assert log is not None


def test_poll_analysis_job_complete(client, auth_headers):
    resp = _analyse(client, auth_headers)
    job_id = resp.json()["job_id"]
    job_resp = client.get(f"/compliance-checks/{job_id}", headers=auth_headers)
    assert job_resp.json()["status"] == "Complete"


# ── Tests: GET /proposals/{id} ───────────────────────────────────────────────

def test_get_proposal_with_findings_and_suggestions(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    p = client.get(f"/proposals/{proposal_id}", headers=auth_headers).json()
    assert p["status"] == "Pending"
    assert len(p["findings"]) == 2
    assert len(p["suggestions"]) == 2
    assert p["inferred_purpose"] == "Customer service chatbot"
    assert p["inferred_risk_tier"] == "Limited"


def test_proposal_not_found(client, auth_headers):
    resp = client.get("/proposals/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


# ── Tests: POST /proposals/{id}/responses ────────────────────────────────────

def test_record_accepted_response(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    resp2 = _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    assert resp2.status_code == 200

    log = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "UpgradeResponseRecorded",
    ).first()
    assert log is not None


def test_record_rejected_response(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    resp2 = _respond(client, auth_headers, proposal_id, "s-001", "Rejected", user_note="Not needed")
    assert resp2.status_code == 200


def test_each_response_creates_separate_audit(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Rejected")
    logs = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "UpgradeResponseRecorded",
    ).all()
    assert len(logs) == 2


def test_response_on_applied_proposal_returns_409(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    # Create a prompt to link to
    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Accepted")
    client.post(f"/proposals/{proposal_id}/apply", json={"prompt_id": prompt_id}, headers=auth_headers)

    resp2 = _respond(client, auth_headers, proposal_id, "s-001", "Rejected")
    assert resp2.status_code == 409


# ── Tests: POST /proposals/{id}/apply ────────────────────────────────────────

def test_apply_returns_422_when_responses_missing(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    # s-002 missing
    resp2 = client.post(f"/proposals/{proposal_id}/apply", headers=auth_headers)
    assert resp2.status_code == 422
    assert "s-002" in resp2.json()["detail"]


def test_apply_creates_version_and_queues_compliance(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Rejected")

    resp2 = client.post(
        f"/proposals/{proposal_id}/apply",
        json={"prompt_id": prompt_id},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert "version_id" in data
    assert "compliance_job_id" in data


def test_apply_sets_upgrade_proposal_id_on_version(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Accepted")

    resp2 = client.post(
        f"/proposals/{proposal_id}/apply",
        json={"prompt_id": prompt_id},
        headers=auth_headers,
    )
    version_id = resp2.json()["version_id"]
    version = db.query(PromptVersion).filter(PromptVersion.version_id == version_id).first()
    assert version.upgrade_proposal_id == proposal_id


def test_apply_writes_audit_log(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Accepted")
    client.post(f"/proposals/{proposal_id}/apply", json={"prompt_id": prompt_id}, headers=auth_headers)

    log = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "UpgradeApplied",
    ).first()
    assert log is not None


def test_apply_sets_proposal_status_applied(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Accepted")
    client.post(f"/proposals/{proposal_id}/apply", json={"prompt_id": prompt_id}, headers=auth_headers)

    p = client.get(f"/proposals/{proposal_id}", headers=auth_headers).json()
    assert p["status"] == "Applied"
    assert p["resulting_version_id"] is not None


# ── Tests: POST /proposals/{id}/abandon ──────────────────────────────────────

def test_abandon_sets_status_and_reason(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    resp2 = client.post(
        f"/proposals/{proposal_id}/abandon",
        json={"reason": "Rewriting from scratch"},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "Abandoned"
    assert resp2.json()["abandoned_reason"] == "Rewriting from scratch"


def test_abandon_writes_audit_log(client, auth_headers, db):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]
    client.post(
        f"/proposals/{proposal_id}/abandon",
        json={"reason": "Not needed"},
        headers=auth_headers,
    )
    log = db.query(AuditLog).filter(
        AuditLog.entity_id == proposal_id,
        AuditLog.action == "UpgradeAbandoned",
    ).first()
    assert log is not None


def test_abandon_applied_proposal_returns_409(client, auth_headers):
    resp = _analyse(client, auth_headers)
    proposal_id = resp.json()["proposal_id"]

    prompt_resp = _create_prompt(client, auth_headers)
    prompt_id = prompt_resp.json()["prompt_id"]

    _respond(client, auth_headers, proposal_id, "s-001", "Accepted")
    _respond(client, auth_headers, proposal_id, "s-002", "Accepted")
    client.post(f"/proposals/{proposal_id}/apply", json={"prompt_id": prompt_id}, headers=auth_headers)

    resp2 = client.post(
        f"/proposals/{proposal_id}/abandon",
        json={"reason": "too late"},
        headers=auth_headers,
    )
    assert resp2.status_code == 409
