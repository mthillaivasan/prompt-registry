"""
Tests for the Build → Deployment gate (Block 22 — F21.1 fix).

Same shape as the deployment gate tests: synthetic prompt + a build
ComplianceRun + a Checker user; verify role enforcement, rationale
enforcement, blocked-on-Fail-run, idempotency.
"""

import json
import re

import pytest

from app.auth import hash_password
from app.models import GateDecision, User
from services.compliance_engine import run_phase_compliance


def _build_run(db, version_id, score=5):
    def fake(system_prompt, _user):
        codes = re.findall(r"- ([A-Z0-9_]+) \(", system_prompt)
        return json.dumps({"scores": {c: {"score": score, "rationale": "ok"} for c in codes}})

    return run_phase_compliance(
        db,
        phase_code="build",
        subject_type="prompt_version",
        subject_id=version_id,
        run_by="SYSTEM",
        scoring_input_text="dummy",
        metadata={"prompt_type": "Analysis", "input_type": "Plain text", "risk_tier": "Limited"},
        score_provider=fake,
    )


def _create_prompt(client, headers):
    payload = {
        "title": "Build gate test",
        "prompt_type": "Analysis",
        "deployment_target": "OpenAI",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "review_cadence_days": 90,
        "prompt_text": "x",
        "change_summary": "v1",
    }
    return client.post("/prompts", json=payload, headers=headers).json()


def _checker(client, db):
    email = "build-gate-checker@test.local"
    existing = db.query(User).filter(User.email == email).first()
    if existing is None:
        existing = User(
            email=email, name="C", role="Checker",
            password_hash=hash_password("p"), is_active=True,
        )
        db.add(existing)
        db.commit()
    token = client.post(
        "/auth/login", data={"username": email, "password": "p"},
    ).json()["access_token"]
    return existing, {"Authorization": f"Bearer {token}"}


def test_build_gate_requires_run(client, auth_headers, db):
    """No compliance run → 409."""
    p = _create_prompt(client, auth_headers)
    _checker_user, checker_headers = _checker(client, db)
    resp = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "fine"},
        headers=checker_headers,
    )
    assert resp.status_code == 409
    assert "compliance run" in resp.json()["detail"].lower()


def test_build_gate_rejects_maker(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    resp = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "fine"},
        headers=auth_headers,  # Maker
    )
    assert resp.status_code == 403


def test_build_gate_approves_with_checker(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    resp = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "Reviewed; pass."},
        headers=checker_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decision"] == "Approved"
    assert body["gate_code"] == "build_to_deployment"


def test_build_gate_rationale_required(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    resp = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved"},
        headers=checker_headers,
    )
    assert resp.status_code == 422


def test_build_gate_blocks_approval_on_fail(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"], score=1)
    _checker_user, checker_headers = _checker(client, db)
    resp = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "still want it"},
        headers=checker_headers,
    )
    assert resp.status_code == 409


def test_build_gate_idempotent_409_on_second_call(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    first = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    assert first.status_code == 201
    second = client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    assert second.status_code == 409


def test_build_gate_marks_version_approved(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    from app.models import PromptVersion
    db.expire_all()
    version = db.query(PromptVersion).filter(PromptVersion.version_id == p["versions"][0]["version_id"]).first()
    assert version.approved_by == _checker_user.user_id
    assert version.approved_at is not None


def test_build_gate_dashboard_marker_lights_up(client, auth_headers, db):
    """The motivating fix: dashboard's build_gate marker should populate
    after the gate fires."""
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    dash = client.get("/dashboard?owner=all", headers=auth_headers).json()
    row = next(r for r in dash["prompts"] if r["prompt_id"] == p["prompt_id"])
    assert row["build_gate"] is not None
    assert row["build_gate"]["rationale"] == "ok"


def test_list_build_gate_decisions(client, auth_headers, db):
    p = _create_prompt(client, auth_headers)
    _build_run(db, p["versions"][0]["version_id"])
    _checker_user, checker_headers = _checker(client, db)
    client.post(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decision",
        json={"decision": "Approved", "rationale": "ok"},
        headers=checker_headers,
    )
    resp = client.get(
        f"/prompt-versions/{p['versions'][0]['version_id']}/gate-decisions",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
