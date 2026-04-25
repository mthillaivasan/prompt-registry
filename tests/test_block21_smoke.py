"""
Block 21 — End-to-end smoke pass.

Drives one prompt from Brief → Build → gate → Deployment → gate →
Operation against the live HTTP endpoints. The Claude scorer is stubbed
(no network) so the test is reproducible; observations from running it
are recorded in VALIDATION_LOG.md.

This file is intentionally dense. It is the longest test in the suite
because it exercises the longest path. It is a single test on purpose:
splitting it would lose the friction-of-the-flow signal that motivates
Block 21.
"""

import json
import re

import pytest

from app.auth import hash_password
from app.models import (
    AuditLog,
    Brief,
    ComplianceRun,
    DeploymentRecord,
    GateDecision,
    OperationRecord,
    Phase,
    User,
)
from services.compliance_engine import run_phase_compliance


def _fake_score(system_prompt, _user_message):
    """All-fives stub that responds to whatever dimensions are listed."""
    codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
    return json.dumps({"scores": {c: {"score": 5, "rationale": "ok"} for c in codes}})


def _checker(client, db):
    email = "smoke-checker@test.local"
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        existing = User(
            email=email, name="Smoke Checker", role="Checker",
            password_hash=hash_password("checkerpass"), is_active=True,
        )
        db.add(existing)
        db.commit()
    token = client.post(
        "/auth/login", data={"username": email, "password": "checkerpass"},
    ).json()["access_token"]
    return existing, {"Authorization": f"Bearer {token}"}


def test_block21_smoke_full_lifecycle(client, auth_headers, test_user, db, monkeypatch):
    monkeypatch.setattr("services.compliance_engine._call_claude", _fake_score)

    # -----------------------------------------------------------------
    # Stage 1: Brief Builder
    # -----------------------------------------------------------------
    brief = client.post(
        "/briefs",
        json={
            "client_name": "Acme Corp",
            "business_owner_name": "Jane Approver",
            "business_owner_role": "Head of Risk",
        },
        headers=auth_headers,
    ).json()
    brief_id = brief["brief_id"]

    # Set the title via PATCH (status is not user-editable through PATCH;
    # the wizard calls POST /briefs/{id}/complete to finalise).
    title_patch = client.patch(
        f"/briefs/{brief_id}",
        json={"title": "Loan default risk summariser"},
        headers=auth_headers,
    )
    assert title_patch.status_code == 200
    completed = client.post(f"/briefs/{brief_id}/complete", headers=auth_headers)
    assert completed.status_code == 200, completed.text

    # -----------------------------------------------------------------
    # Stage 2: Build artefact (a prompt + its v1 version)
    # -----------------------------------------------------------------
    p = client.post(
        "/prompts",
        json={
            "title": "Loan default risk summariser",
            "prompt_type": "Summarisation",
            "deployment_target": "Anthropic",
            "input_type": "document",
            "output_type": "Plain text",
            "risk_tier": "Limited",
            "review_cadence_days": 90,
            "prompt_text": (
                "You are a regulated AI assistant operating under the FCA "
                "consumer credit framework. Summarise the supplied loan "
                "application in three bullets. Mark output advisory and "
                "name the human reviewer in the audit trail."
            ),
            "change_summary": "v1 — initial draft from brief",
        },
        headers=auth_headers,
    ).json()
    prompt_id = p["prompt_id"]
    version_id = p["versions"][0]["version_id"]

    # Link the brief to the prompt so the dashboard shows ✓ Complete on Brief
    db.query(Brief).filter(Brief.brief_id == brief_id).update(
        {"resulting_prompt_id": prompt_id}
    )
    db.commit()

    # -----------------------------------------------------------------
    # Stage 3: Build compliance via the new engine (write a run)
    # -----------------------------------------------------------------
    build_run = run_phase_compliance(
        db,
        phase_code="build",
        subject_type="prompt_version",
        subject_id=version_id,
        run_by=test_user.user_id,
        scoring_input_text=p["versions"][0]["prompt_text"],
        metadata={
            "prompt_type": "Summarisation",
            "input_type": "document",
            "risk_tier": "Limited",
        },
        score_provider=_fake_score,
    )
    assert build_run.overall_result in ("Pass", "Pass with warnings")

    # -----------------------------------------------------------------
    # Stage 4: Build → Deployment gate (manually fire — there's no
    # /prompt-versions/{id}/gate-decision endpoint yet; gate_decisions
    # is written ad-hoc here. *** Block 22 candidate: the Build gate
    # endpoint is missing; the dashboard's build_gate marker therefore
    # never lights up for the real flow.)
    # -----------------------------------------------------------------
    from app.models import Gate
    build_phase = db.query(Phase).filter(Phase.code == "build").one()
    build_gate = db.query(Gate).filter(Gate.from_phase_id == build_phase.phase_id).one()
    _checker_user, checker_headers = _checker(client, db)
    decision = GateDecision(
        gate_id=build_gate.gate_id,
        subject_type="prompt_version",
        subject_id=version_id,
        run_id=build_run.run_id,
        decision="Approved",
        decided_by=_checker_user.user_id,
        rationale="Build run scored Pass; dimensions look clean.",
    )
    db.add(decision)
    db.commit()

    # -----------------------------------------------------------------
    # Stage 5: Deployment record + form submission
    # -----------------------------------------------------------------
    deployment_id = client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=auth_headers,
    ).json()["deployment_id"]

    full_form = {
        "invocation_trigger": "scheduled_job",
        "invocation_frequency_per_day": "10-100",
        "latency_envelope_seconds": "10",
        "input_data_categories": ["client_confidential", "regulatory_filings"],
        "input_redaction_applied": True,
        "input_size_p95_tokens": "4096",
        "input_user_supplied": False,
        "output_destination": "human_review_only",
        "output_executed_by_machine": False,
        "output_storage_retention_days": "365",
        "logging_destination": "audit_log_table",
        "metric_collection": ["latency", "error_rate", "output_quality_sample"],
        "alerting_thresholds_defined": True,
        "runtime_owner_id": test_user.user_id,
        "approver_id": _checker_user.user_id,
        "change_review_frequency_days": "180",
        "breaking_change_protocol": "Notify business owner via change-management mailbox; 5-day review window.",
        "model_provider": "Anthropic",
        "data_residency": "UK",
        "sub_processing_disclosed": True,
        "audit_rights_in_contract": True,
    }
    put_resp = client.put(
        f"/deployments/{deployment_id}",
        json={"responses": full_form},
        headers=auth_headers,
    )
    assert put_resp.json()["errors"] == {}

    submit = client.post(f"/deployments/{deployment_id}/submit", headers=auth_headers)
    assert submit.status_code == 200, submit.text

    # -----------------------------------------------------------------
    # Stage 6: Deployment compliance run
    # -----------------------------------------------------------------
    deploy_run = client.post(
        f"/deployments/{deployment_id}/compliance",
        headers=auth_headers,
    )
    assert deploy_run.status_code == 201, deploy_run.text
    deploy_body = deploy_run.json()
    assert deploy_body["overall_result"] in ("Pass", "Pass with warnings")
    # Each scored dimension carries a standards label
    assert all("standard" in s and s["standard"]["standard_code"] for s in deploy_body["scores"])

    # -----------------------------------------------------------------
    # Stage 7: Deployment → Operation gate
    # -----------------------------------------------------------------
    gate = client.post(
        f"/deployments/{deployment_id}/gate-decision",
        json={"decision": "Approved", "rationale": "Runtime config matches build declarations; sign-off."},
        headers=checker_headers,
    )
    assert gate.status_code == 201, gate.text

    # -----------------------------------------------------------------
    # Stage 8: Operation record auto-created; cadence honoured
    # -----------------------------------------------------------------
    op = (
        db.query(OperationRecord)
        .filter(OperationRecord.deployment_id == deployment_id)
        .one()
    )
    assert op.state == "Active"
    assert op.review_cadence_days == 180  # from form response

    # Append an incident (Medium — does not flip state)
    inc = client.post(
        f"/operation/{op.operation_id}/incidents",
        json={"severity": "Medium", "category": "Quality", "summary": "One output sample flagged ambiguous."},
        headers=auth_headers,
    )
    assert inc.status_code == 201
    db.refresh(op)
    assert op.state == "Active"

    # Run an Operation compliance check
    run = client.post(f"/operation/{op.operation_id}/run", headers=auth_headers)
    assert run.status_code == 201

    # -----------------------------------------------------------------
    # Stage 9: Dashboard renders the row at-operation
    # -----------------------------------------------------------------
    dash = client.get("/dashboard?owner=all", headers=auth_headers).json()
    row = next(r for r in dash["prompts"] if r["prompt_id"] == prompt_id)
    assert row["brief"]["state"] == "Complete"
    assert row["build"]["state"] in ("Pass", "PWW")
    assert row["deployment"]["state"] == "Approved"
    assert row["deployment_gate"] is not None  # gate marker rendered
    assert row["operation"]["state"] == "Active"

    # -----------------------------------------------------------------
    # Stage 10: Audit trail
    # -----------------------------------------------------------------
    audit = (
        db.query(AuditLog)
        .filter(AuditLog.entity_id == deployment_id)
        .order_by(AuditLog.timestamp)
        .all()
    )
    actions = [a.action for a in audit]
    # Order is the lifecycle of a deployment record:
    # Created (Block 13) → Edited (submit) → ComplianceChecked → Approved
    assert "Created" in actions
    assert "Edited" in actions
    assert "ComplianceChecked" in actions
    assert "Approved" in actions
