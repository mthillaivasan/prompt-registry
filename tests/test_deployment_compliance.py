"""
Tests for the Deployment-phase compliance engine (Block 15).

Synthetic fixtures use TEST_* codes so the engine cannot match against
production seed data — the same discipline as test_compliance_v2.py.

Then a round-trip test exercises the production seed (the four real
Deployment-tagged dimensions): Block 14's must-pass logic, applicability
flags, and gate evaluation.
"""

import json

import pytest

from app.models import (
    DeploymentRecord,
    Dimension,
    Gate,
    GateMustPassDimension,
    Phase,
    PhaseWeight,
    Prompt,
    PromptVersion,
    Standard,
)
from services import applicability, deployment_compliance


# ── Pure unit tests for new applicability rules ─────────────────────────────

def test_applicability_flag_true():
    rule = {"if_flag_is_true": "input_user_supplied"}
    assert applicability.evaluate(rule, {"input_user_supplied": True}) is True
    assert applicability.evaluate(rule, {"input_user_supplied": False}) is False
    assert applicability.evaluate(rule, {}) is False


def test_applicability_flag_false():
    rule = {"if_flag_is_false": "alerting_thresholds_defined"}
    assert applicability.evaluate(rule, {"alerting_thresholds_defined": False}) is True
    assert applicability.evaluate(rule, {"alerting_thresholds_defined": True}) is False
    # Missing key is treated as falsey
    assert applicability.evaluate(rule, {}) is True


# ── Serialiser ──────────────────────────────────────────────────────────────

def _create_prompt_and_version(client, headers):
    payload = {
        "title": "Compliance test prompt",
        "prompt_type": "Analysis",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 180,
        "prompt_text": "Analyse the supplied text.",
        "change_summary": "v1",
    }
    resp = client.post("/prompts", json=payload, headers=headers)
    assert resp.status_code == 201
    body = resp.json()
    return body["prompt_id"], body["versions"][0]["version_id"]


def _seed_responses_for(test_user_id, **overrides):
    base = {
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
    base.update(overrides)
    return base


def test_serialiser_emits_prompt_block_and_form_fields(db, client, auth_headers, test_user):
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    rec = DeploymentRecord(
        prompt_id=prompt_id,
        version_id=version_id,
        runtime_owner_id=test_user.user_id,
        form_responses_json=json.dumps(_seed_responses_for(test_user.user_id)),
        status="Pending Approval",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    text, metadata = deployment_compliance.serialise_deployment_record(db, rec)
    assert "PROMPT_TITLE: Compliance test prompt" in text
    assert "PROMPT_TYPE: Analysis" in text
    assert "DEPLOYMENT_INVOCATION_TRIGGER: manual_user_action" in text
    assert "DEPLOYMENT_MODEL_PROVIDER: Anthropic" in text
    assert "DEPLOYMENT_INPUT_DATA_CATEGORIES: public_information" in text
    # Booleans rendered as lowercase strings
    assert "DEPLOYMENT_INPUT_REDACTION_APPLIED: true" in text

    # Metadata flags
    assert metadata["prompt_type"] == "Analysis"
    assert metadata["risk_tier"] == "Limited"
    assert metadata["input_user_supplied"] is False
    assert metadata["output_executed_by_machine"] is False
    assert metadata["personal_data_present"] is False


def test_serialiser_personal_data_flag(db, client, auth_headers, test_user):
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    rec = DeploymentRecord(
        prompt_id=prompt_id,
        version_id=version_id,
        runtime_owner_id=test_user.user_id,
        form_responses_json=json.dumps(_seed_responses_for(
            test_user.user_id,
            input_data_categories=["personal_data", "client_confidential"],
            input_user_supplied=True,
            output_executed_by_machine=True,
        )),
        status="Pending Approval",
    )
    db.add(rec)
    db.commit()
    _text, metadata = deployment_compliance.serialise_deployment_record(db, rec)
    assert metadata["personal_data_present"] is True
    assert metadata["input_user_supplied"] is True
    assert metadata["output_executed_by_machine"] is True


# ── End-to-end with synthetic Deployment-phase fixture ──────────────────────

@pytest.fixture
def synthetic_deployment_phase(db):
    """A synthetic Deployment phase. TEST_* codes only — proves engine
    is generic and does not branch on production phase or dimension
    identity."""
    s_alpha = Standard(
        standard_code="TEST_DEPLOY_STD",
        title="Test deploy std",
        version="1",
        publisher="Test",
    )
    db.add(s_alpha)
    db.flush()

    p = Phase(
        code="test_deploy_phase",
        title="Test deploy phase",
        purpose="for tests",
        scoring_input="deployment_record",
        sort_order=98,
    )
    db.add(p)
    db.flush()

    db.add(PhaseWeight(phase_id=p.phase_id, standard_id=s_alpha.standard_id, weight="1.0"))

    dims = [
        Dimension(
            code="TEST_DEPLOY_DIM_USER_INPUT",
            title="Runtime user-input check",
            phase_id=p.phase_id,
            standard_id=s_alpha.standard_id,
            sort_order=1,
            blocking_threshold=2,
            is_mandatory=True,
            scoring_type="Blocking",
            applicability=json.dumps({"if_flag_is_true": "input_user_supplied"}),
            score_5_criteria="all good",
            score_3_criteria="ok",
            score_1_criteria="bad",
        ),
        Dimension(
            code="TEST_DEPLOY_DIM_ALWAYS",
            title="Always-on deploy dim",
            phase_id=p.phase_id,
            standard_id=s_alpha.standard_id,
            sort_order=2,
            blocking_threshold=2,
            is_mandatory=True,
            scoring_type="Advisory",
            applicability=json.dumps({"always": True}),
            score_5_criteria="all good",
            score_3_criteria="ok",
            score_1_criteria="bad",
        ),
    ]
    db.add_all(dims)
    db.flush()

    g = Gate(
        code="test_deploy_gate",
        title="Test deploy gate",
        from_phase_id=p.phase_id,
        min_grade="3.0",
        approver_role="Checker",
    )
    db.add(g)
    db.flush()
    db.add(GateMustPassDimension(gate_id=g.gate_id, dimension_id=dims[0].dimension_id))
    db.add(GateMustPassDimension(gate_id=g.gate_id, dimension_id=dims[1].dimension_id))

    db.commit()
    return {"phase_code": "test_deploy_phase", "phase_id": p.phase_id}


def test_synthetic_deployment_excludes_user_input_dim_when_flag_off(
    db, client, auth_headers, test_user, synthetic_deployment_phase
):
    """User-input dimension's applicability rule is `if_flag_is_true:
    input_user_supplied`. With the flag false, only the always-on dim
    should appear in scoring."""
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    rec = DeploymentRecord(
        prompt_id=prompt_id,
        version_id=version_id,
        runtime_owner_id=test_user.user_id,
        form_responses_json=json.dumps(_seed_responses_for(test_user.user_id)),
        status="Pending Approval",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    seen_codes: list[str] = []

    def fake_score(system_prompt, _user_message):
        for code in ("TEST_DEPLOY_DIM_USER_INPUT", "TEST_DEPLOY_DIM_ALWAYS"):
            if code in system_prompt:
                seen_codes.append(code)
        return json.dumps({"scores": {
            code: {"score": 5, "rationale": "ok"} for code in seen_codes
        }})

    # Direct call to engine with the synthetic phase code so we exercise
    # the same code path the deployment compliance helper uses.
    from services.compliance_engine import run_phase_compliance
    run = run_phase_compliance(
        db,
        phase_code="test_deploy_phase",
        subject_type="deployment_record",
        subject_id=rec.deployment_id,
        run_by="SYSTEM",
        scoring_input_text="...",
        metadata={"input_user_supplied": False},
        score_provider=fake_score,
    )
    assert "TEST_DEPLOY_DIM_USER_INPUT" not in seen_codes
    assert "TEST_DEPLOY_DIM_ALWAYS" in seen_codes
    assert run.overall_result in ("Pass", "Pass with warnings")


def test_synthetic_deployment_includes_user_input_dim_when_flag_on(
    db, client, auth_headers, test_user, synthetic_deployment_phase
):
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    rec = DeploymentRecord(
        prompt_id=prompt_id,
        version_id=version_id,
        runtime_owner_id=test_user.user_id,
        form_responses_json=json.dumps(_seed_responses_for(
            test_user.user_id, input_user_supplied=True
        )),
        status="Pending Approval",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    seen_codes: list[str] = []

    def fake_score(system_prompt, _user_message):
        for code in ("TEST_DEPLOY_DIM_USER_INPUT", "TEST_DEPLOY_DIM_ALWAYS"):
            if code in system_prompt:
                seen_codes.append(code)
        return json.dumps({"scores": {
            code: {"score": 1, "rationale": "fail"} for code in seen_codes
        }})

    from services.compliance_engine import run_phase_compliance
    run = run_phase_compliance(
        db,
        phase_code="test_deploy_phase",
        subject_type="deployment_record",
        subject_id=rec.deployment_id,
        run_by="SYSTEM",
        scoring_input_text="...",
        metadata={"input_user_supplied": True},
        score_provider=fake_score,
    )
    assert "TEST_DEPLOY_DIM_USER_INPUT" in seen_codes
    # Score 1 fails the gate
    assert run.overall_result == "Fail"


# ── End-to-end via the production seed ──────────────────────────────────────

def test_run_deployment_compliance_via_router(client, auth_headers, test_user, db, monkeypatch):
    """Production-seed end-to-end. Stubs the Claude call so the router
    path is exercised without an LLM network hit. The point is to prove
    the engine, the seed, and the router compose; not to assert anything
    about specific dimension codes."""
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    create = client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=auth_headers,
    )
    deployment_id = create.json()["deployment_id"]

    client.put(
        f"/deployments/{deployment_id}",
        json={"responses": _seed_responses_for(test_user.user_id)},
        headers=auth_headers,
    )
    submit = client.post(
        f"/deployments/{deployment_id}/submit",
        headers=auth_headers,
    )
    assert submit.status_code == 200, submit.text

    # Stub the LLM call path. The serialiser feeds whatever applicable
    # dimensions are listed; we award them all 5s.
    def fake_call(system_prompt, _user_message):
        # Extract codes from `- CODE (` lines in the prompt
        import re
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": 5, "rationale": "stub"} for c in codes}})

    monkeypatch.setattr(
        "services.compliance_engine._call_claude", fake_call
    )

    resp = client.post(
        f"/deployments/{deployment_id}/compliance",
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["overall_result"] in ("Pass", "Pass with warnings")
    # Each scored dimension must carry a standard label.
    for s in body["scores"]:
        assert "standard" in s
        assert s["standard"]["standard_code"]


def test_run_compliance_requires_pending_approval(client, auth_headers, test_user, db):
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    create = client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=auth_headers,
    )
    deployment_id = create.json()["deployment_id"]
    # Still in Draft
    resp = client.post(
        f"/deployments/{deployment_id}/compliance",
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_get_compliance_returns_404_when_no_run(client, auth_headers):
    prompt_id, version_id = _create_prompt_and_version(client, auth_headers)
    create = client.post(
        "/deployments",
        json={"prompt_id": prompt_id, "version_id": version_id},
        headers=auth_headers,
    )
    deployment_id = create.json()["deployment_id"]
    resp = client.get(f"/deployments/{deployment_id}/compliance", headers=auth_headers)
    assert resp.status_code == 404
