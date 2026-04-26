"""Tests for compliance engine — Session 3."""

import json
from unittest.mock import patch

from app.models import AuditLog, ComplianceCheck, PromptVersion, ScoringDimension
from services.compliance_engine import (
    build_system_prompt,
    compute_gold_standard,
    count_blocking_defects,
    determine_overall_result,
    get_active_dimensions,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _create_prompt_and_version(client, auth_headers):
    """Create a prompt with v1 and return (prompt_id, version_id)."""
    resp = client.post("/prompts", json={
        "title": "Compliance test prompt",
        "prompt_type": "Governance",
        "deployment_target": "Internal",
        "input_type": "Plain text",
        "output_type": "Plain text",
        "risk_tier": "Limited",
        "prompt_text": "You are a helpful assistant. Answer questions about compliance.",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    return data["prompt_id"], data["versions"][0]["version_id"]


def _mock_scores(dims, reg_score=4, other_score=4):
    """Build a mock scoring response with configurable scores."""
    scores = {}
    for d in dims:
        s = reg_score if d.framework == "REGULATORY" else other_score
        scores[d.code] = {"score": s, "rationale": f"Test score for {d.name}"}
    return {"scores": scores}


def _mock_scoring_json(dims, reg_score=4, other_score=4):
    return json.dumps(_mock_scores(dims, reg_score, other_score))


MOCK_ANOMALY_CLEAN = json.dumps({
    "result": "clean",
    "confidence": 0.95,
    "reason": "Output follows expected structure",
})


def _mock_call_claude_factory(dims, reg_score=4, other_score=4):
    call_count = [0]
    scoring_json = _mock_scoring_json(dims, reg_score, other_score)

    def mock_call(system_prompt, user_message):
        call_count[0] += 1
        if call_count[0] % 2 == 1:
            return scoring_json
        return MOCK_ANOMALY_CLEAN

    return mock_call, call_count


# ── Dimension tests ──────────────────────────────────────────────────────────

def test_active_dimensions_loaded(db):
    dims = get_active_dimensions(db)
    assert len(dims) == 17


def test_dimension_frameworks(db):
    dims = get_active_dimensions(db)
    frameworks = {d.framework for d in dims}
    assert frameworks == {"REGULATORY", "OWASP", "NIST", "ISO42001"}


def test_regulatory_dimensions_are_mandatory(db):
    dims = get_active_dimensions(db)
    for d in dims:
        if d.framework == "REGULATORY":
            assert d.is_mandatory is True
            assert d.blocking_threshold == 2


# ── System prompt tests ──────────────────────────────────────────────────────

def test_system_prompt_built_dynamically(db):
    dims = get_active_dimensions(db)
    prompt = build_system_prompt(dims)
    assert "REGULATORY" in prompt
    assert "OWASP" in prompt
    assert "NIST" in prompt
    assert "ISO42001" in prompt
    assert "REG_D1" in prompt
    assert "OWASP_LLM01" in prompt
    assert "{prompt_text}" in prompt  # placeholder present


def test_system_prompt_includes_criteria(db):
    dims = get_active_dimensions(db)
    prompt = build_system_prompt(dims)
    assert "Score 5:" in prompt
    assert "Score 3:" in prompt
    assert "Score 1:" in prompt


# ── Gold standard tests ─────────────────────────────────────────────────────

def test_gold_score_all_fives(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=5, other_score=5)
    gold = compute_gold_standard(scores, dims)
    assert gold["composite"] == 100.0


def test_gold_score_all_ones(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=1, other_score=1)
    gold = compute_gold_standard(scores, dims)
    assert gold["composite"] == 0.0


def test_gold_score_has_framework_averages(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=3, other_score=5)
    gold = compute_gold_standard(scores, dims)
    assert "REGULATORY" in gold["framework_averages"]
    assert "OWASP" in gold["framework_averages"]
    assert gold["framework_averages"]["REGULATORY"] == 3.0
    assert gold["framework_averages"]["OWASP"] == 5.0


# ── Blocking tests ───────────────────────────────────────────────────────────

def test_blocking_when_reg_score_1(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=1, other_score=5)
    count, defects = count_blocking_defects(scores, dims)
    assert count == 6  # all 6 REG dimensions
    assert all(d["score"] == 1 for d in defects)


def test_blocking_when_reg_score_2(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=2, other_score=5)
    count, _ = count_blocking_defects(scores, dims)
    assert count == 6


def test_not_blocked_when_reg_score_3(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=3, other_score=5)
    count, _ = count_blocking_defects(scores, dims)
    assert count == 0


def test_owasp_low_score_does_not_block(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=5, other_score=1)
    count, _ = count_blocking_defects(scores, dims)
    assert count == 0


def test_overall_result_fail(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=1)
    assert determine_overall_result(6, scores, dims) == "Fail"


def test_overall_result_pass_with_warnings(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=3, other_score=3)
    assert determine_overall_result(0, scores, dims) == "Pass with warnings"


def test_overall_result_pass(db):
    dims = get_active_dimensions(db)
    scores = _mock_scores(dims, reg_score=5, other_score=5)
    assert determine_overall_result(0, scores, dims) == "Pass"


# ── API endpoint tests ──────────────────────────────────────────────────────

def test_compliance_check_requires_auth(client):
    resp = client.post("/compliance-checks", json={"version_id": "x"})
    assert resp.status_code == 401


def test_compliance_check_404_for_unknown_version(client, auth_headers):
    resp = client.post("/compliance-checks", json={
        "version_id": "00000000-0000-0000-0000-000000000000",
    }, headers=auth_headers)
    assert resp.status_code == 404


def test_compliance_check_end_to_end(client, auth_headers, db):
    _, version_id = _create_prompt_and_version(client, auth_headers)
    dims = get_active_dimensions(db)
    mock_call, call_count = _mock_call_claude_factory(dims, reg_score=4, other_score=4)

    with patch("services.compliance_engine._call_claude", side_effect=mock_call):
        resp = client.post("/compliance-checks", json={
            "version_id": version_id,
        }, headers=auth_headers)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Poll
    job_resp = client.get(f"/compliance-checks/{job_id}", headers=auth_headers)
    assert job_resp.status_code == 200
    job = job_resp.json()
    assert job["status"] == "Complete"
    assert job["result"] is not None
    assert job["result"]["overall_result"] == "Pass"
    assert job["result"]["blocking_defects"] == 0
    assert job["result"]["gold_standard"]["composite"] > 0
    assert len(job["result"]["scores"]) == 17
    assert job["result"]["anomaly"]["result"] == "clean"
    assert call_count[0] == 2  # scoring + anomaly


def test_compliance_check_blocking(client, auth_headers, db):
    _, version_id = _create_prompt_and_version(client, auth_headers)
    dims = get_active_dimensions(db)
    mock_call, _ = _mock_call_claude_factory(dims, reg_score=1, other_score=4)

    with patch("services.compliance_engine._call_claude", side_effect=mock_call):
        resp = client.post("/compliance-checks", json={
            "version_id": version_id,
        }, headers=auth_headers)
    job_id = resp.json()["job_id"]
    job = client.get(f"/compliance-checks/{job_id}", headers=auth_headers).json()
    assert job["result"]["overall_result"] == "Fail"
    assert job["result"]["blocking_defects"] == 6


def test_compliance_check_cached(client, auth_headers, db):
    _, version_id = _create_prompt_and_version(client, auth_headers)
    dims = get_active_dimensions(db)
    mock_call, call_count = _mock_call_claude_factory(dims)

    with patch("services.compliance_engine._call_claude", side_effect=mock_call):
        resp1 = client.post("/compliance-checks", json={"version_id": version_id}, headers=auth_headers)
    assert call_count[0] == 2

    # Second call should hit cache — no new API calls
    call_count[0] = 0
    resp2 = client.post("/compliance-checks", json={"version_id": version_id}, headers=auth_headers)
    assert resp2.json()["status"] == "Complete"
    assert call_count[0] == 0  # cache hit, no calls


def test_compliance_check_force_refresh(client, auth_headers, db):
    _, version_id = _create_prompt_and_version(client, auth_headers)
    dims = get_active_dimensions(db)
    mock_call, call_count = _mock_call_claude_factory(dims)

    with patch("services.compliance_engine._call_claude", side_effect=mock_call):
        client.post("/compliance-checks", json={"version_id": version_id}, headers=auth_headers)
    first_calls = call_count[0]

    with patch("services.compliance_engine._call_claude", side_effect=mock_call):
        client.post("/compliance-checks", json={
            "version_id": version_id,
            "force_refresh": True,
        }, headers=auth_headers)
    assert call_count[0] > first_calls


def test_job_not_found(client, auth_headers):
    resp = client.get("/compliance-checks/00000000-0000-0000-0000-000000000000", headers=auth_headers)
    assert resp.status_code == 404


def test_list_scoring_dimensions(client, auth_headers):
    resp = client.get("/scoring-dimensions", headers=auth_headers)
    assert resp.status_code == 200
    dims = resp.json()
    assert len(dims) == 17
    codes = {d["code"] for d in dims}
    assert "REG_D1" in codes
    assert "OWASP_LLM01" in codes


def test_list_wrapper_metadata_dimensions(client, auth_headers):
    """Item 2: governance-context endpoint returns exactly the five
    wrapper_metadata dims and excludes prompt_content / registry_policy."""
    resp = client.get("/scoring-dimensions/wrapper-metadata", headers=auth_headers)
    assert resp.status_code == 200
    dims = resp.json()
    codes = {d["code"] for d in dims}
    assert codes == {"REG_D1", "REG_D4", "REG_D5", "NIST_GOVERN_1", "NIST_MAP_1"}
    # Shape check — each row carries the fields the panel renders
    for d in dims:
        assert d["name"]
        assert d["source_reference"]
        assert d["description"]
        assert d["score_5_criteria"]
    # Negative — prompt_content (REG_D2) and registry_policy (REG_D6) excluded
    assert "REG_D2" not in codes
    assert "REG_D6" not in codes
