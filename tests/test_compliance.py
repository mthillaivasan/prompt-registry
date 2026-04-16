import json
from unittest.mock import patch

from app.compliance_engine import (
    FRAMEWORK_WEIGHTS,
    _build_system_prompt,
    _check_blocked,
    _compute_gold_score,
    _dimensions_hash,
    _get_active_dimensions,
    invalidate_cache_for_dimension_change,
)
from app.models import ComplianceResult, ScoringDimension


def _create_prompt(client, name="compliance-test"):
    return client.post("/prompts", json={
        "name": name,
        "description": "A prompt for compliance testing",
        "tags": ["test"],
        "content": "You are a helpful assistant. Answer the user's question.",
    })


def _mock_scoring_response(dimensions):
    """Build a mock Claude scoring response with all scores = 4."""
    scores = {}
    for d in dimensions:
        scores[d.code] = {"score": 4, "rationale": f"Good coverage for {d.name}"}
    return json.dumps({"scores": scores})


def _mock_anomaly_response():
    return json.dumps({
        "result": "clean",
        "confidence": 0.95,
        "reason": "Output follows system prompt structure.",
    })


# --- Dimension tests ---

def test_list_dimensions(client):
    resp = client.get("/scoring-dimensions")
    assert resp.status_code == 200
    dims = resp.json()
    assert len(dims) == 17
    frameworks = {d["framework"] for d in dims}
    assert frameworks == {"REG", "OWASP", "NIST", "ISO"}


def test_dimension_counts_by_framework(client):
    resp = client.get("/scoring-dimensions")
    dims = resp.json()
    counts = {}
    for d in dims:
        counts[d["framework"]] = counts.get(d["framework"], 0) + 1
    assert counts == {"REG": 6, "OWASP": 5, "NIST": 4, "ISO": 2}


def test_reg_dimensions_are_mandatory(client):
    resp = client.get("/scoring-dimensions")
    reg_dims = [d for d in resp.json() if d["framework"] == "REG"]
    for d in reg_dims:
        assert d["is_mandatory"] is True
        assert d["blocking_threshold"] == 2
        assert d["scoring_type"] == "Blocking"


def test_non_reg_dimensions_are_advisory(client):
    resp = client.get("/scoring-dimensions")
    non_reg = [d for d in resp.json() if d["framework"] != "REG"]
    for d in non_reg:
        assert d["is_mandatory"] is False
        assert d["blocking_threshold"] is None


# --- System prompt tests ---

def test_system_prompt_built_dynamically(db):
    dims = _get_active_dimensions(db)
    prompt = _build_system_prompt(dims)
    assert "You are a regulatory compliance and AI standards assessor." in prompt
    assert "REG_D1" in prompt
    assert "OWASP_LLM01" in prompt
    assert "NIST_GOVERN_1" in prompt
    assert "ISO42001_6_1" in prompt
    assert "{prompt_text}" in prompt


def test_system_prompt_contains_all_frameworks(db):
    dims = _get_active_dimensions(db)
    prompt = _build_system_prompt(dims)
    assert "Frameworks assessed: ISO, NIST, OWASP, REG" in prompt


def test_system_prompt_includes_score_5_criteria(db):
    dims = _get_active_dimensions(db)
    prompt = _build_system_prompt(dims)
    assert "human review" in prompt.lower()
    assert "override path" in prompt.lower()


# --- Gold score tests ---

def test_gold_score_all_fives():
    """All scores = 5 should yield 100."""
    dims = [
        _fake_dim("REG", "REG_D1"), _fake_dim("REG", "REG_D2"),
        _fake_dim("OWASP", "OWASP_LLM01"),
        _fake_dim("NIST", "NIST_GOVERN_1"),
        _fake_dim("ISO", "ISO42001_6_1"),
    ]
    scores = {"scores": {d.code: {"score": 5, "rationale": ""} for d in dims}}
    gold = _compute_gold_score(scores, dims)
    assert gold == 100.0


def test_gold_score_all_ones():
    """All scores = 1 should yield 0."""
    dims = [
        _fake_dim("REG", "REG_D1"),
        _fake_dim("OWASP", "OWASP_LLM01"),
        _fake_dim("NIST", "NIST_GOVERN_1"),
        _fake_dim("ISO", "ISO42001_6_1"),
    ]
    scores = {"scores": {d.code: {"score": 1, "rationale": ""} for d in dims}}
    gold = _compute_gold_score(scores, dims)
    assert gold == 0.0


def test_gold_score_weights():
    """Verify framework weights: REG 40%, OWASP 30%, NIST 20%, ISO 10%."""
    assert FRAMEWORK_WEIGHTS == {"REG": 0.40, "OWASP": 0.30, "NIST": 0.20, "ISO": 0.10}


# --- Blocking tests ---

def test_blocked_when_reg_score_1():
    dims = [_fake_dim("REG", "REG_D1")]
    scores = {"scores": {"REG_D1": {"score": 1, "rationale": ""}}}
    assert _check_blocked(scores, dims) is True


def test_blocked_when_reg_score_2():
    dims = [_fake_dim("REG", "REG_D1")]
    scores = {"scores": {"REG_D1": {"score": 2, "rationale": ""}}}
    assert _check_blocked(scores, dims) is True


def test_not_blocked_when_reg_score_3():
    dims = [_fake_dim("REG", "REG_D1")]
    scores = {"scores": {"REG_D1": {"score": 3, "rationale": ""}}}
    assert _check_blocked(scores, dims) is False


def test_owasp_low_score_does_not_block():
    dims = [_fake_dim("OWASP", "OWASP_LLM01")]
    scores = {"scores": {"OWASP_LLM01": {"score": 1, "rationale": ""}}}
    assert _check_blocked(scores, dims) is False


# --- Cache invalidation tests ---

def test_cache_invalidation(db):
    # Create a fake cached result
    result = ComplianceResult(
        version_id=1,
        scores_json="{}",
        gold_score=50.0,
        blocked=False,
        anomaly_result="clean",
        anomaly_confidence=0.9,
        anomaly_reason="ok",
        cache_valid=True,
        dimensions_hash="abc",
    )
    db.add(result)
    db.commit()

    count = invalidate_cache_for_dimension_change(db)
    assert count == 1
    db.refresh(result)
    assert result.cache_valid is False


# --- Dimensions hash tests ---

def test_dimensions_hash_stable(db):
    dims = _get_active_dimensions(db)
    h1 = _dimensions_hash(dims)
    h2 = _dimensions_hash(dims)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


# --- End-to-end compliance check (mocked Claude) ---

@patch("app.compliance_engine._call_claude")
def test_compliance_check_end_to_end(mock_call, client, db):
    # Create a prompt + version
    create_resp = _create_prompt(client)
    prompt_id = create_resp.json()["id"]
    detail = client.get(f"/prompts/{prompt_id}").json()
    version_id = detail["versions"][0]["id"]

    # Mock Claude calls
    dims = _get_active_dimensions(db)
    mock_call.side_effect = [
        _mock_scoring_response(dims),
        _mock_anomaly_response(),
    ]

    # Submit compliance check
    resp = client.post("/compliance-checks", json={
        "version_id": version_id,
        "requested_by": "test-user",
    })
    assert resp.status_code == 202
    job_data = resp.json()
    assert job_data["version_id"] == version_id
    job_id = job_data["job_id"]

    # Poll for result
    poll = client.get(f"/compliance-jobs/{job_id}")
    assert poll.status_code == 200
    result = poll.json()
    assert result["status"] == "Complete"
    assert result["result"] is not None
    assert result["result"]["blocked"] is False
    assert result["result"]["anomaly"]["result"] == "clean"
    assert len(result["result"]["scores"]) == 17


@patch("app.compliance_engine._call_claude")
def test_compliance_check_cached(mock_call, client, db):
    create_resp = _create_prompt(client, name="cache-test")
    prompt_id = create_resp.json()["id"]
    detail = client.get(f"/prompts/{prompt_id}").json()
    version_id = detail["versions"][0]["id"]

    dims = _get_active_dimensions(db)
    mock_call.side_effect = [
        _mock_scoring_response(dims),
        _mock_anomaly_response(),
    ]

    # First check
    resp1 = client.post("/compliance-checks", json={"version_id": version_id})
    assert resp1.status_code == 202

    # Second check — should use cache, no extra Claude calls
    resp2 = client.post("/compliance-checks", json={"version_id": version_id})
    assert resp2.status_code == 202
    job2 = resp2.json()
    assert job2["status"] == "Complete"
    # Claude was only called twice (scoring + anomaly) for the first check
    assert mock_call.call_count == 2


@patch("app.compliance_engine._call_claude")
def test_compliance_check_force_refresh(mock_call, client, db):
    create_resp = _create_prompt(client, name="refresh-test")
    prompt_id = create_resp.json()["id"]
    detail = client.get(f"/prompts/{prompt_id}").json()
    version_id = detail["versions"][0]["id"]

    dims = _get_active_dimensions(db)
    mock_call.side_effect = [
        _mock_scoring_response(dims),
        _mock_anomaly_response(),
        _mock_scoring_response(dims),
        _mock_anomaly_response(),
    ]

    # First check
    client.post("/compliance-checks", json={"version_id": version_id})

    # Force refresh — should call Claude again
    resp = client.post("/compliance-checks", json={
        "version_id": version_id,
        "force_refresh": True,
    })
    assert resp.status_code == 202
    assert mock_call.call_count == 4


@patch("app.compliance_engine._call_claude")
def test_compliance_check_blocking(mock_call, client, db):
    create_resp = _create_prompt(client, name="blocking-test")
    prompt_id = create_resp.json()["id"]
    detail = client.get(f"/prompts/{prompt_id}").json()
    version_id = detail["versions"][0]["id"]

    dims = _get_active_dimensions(db)
    # Set REG_D1 score to 1 (should block)
    scores = {}
    for d in dims:
        if d.code == "REG_D1":
            scores[d.code] = {"score": 1, "rationale": "Missing human oversight"}
        else:
            scores[d.code] = {"score": 4, "rationale": "Good"}

    mock_call.side_effect = [
        json.dumps({"scores": scores}),
        _mock_anomaly_response(),
    ]

    resp = client.post("/compliance-checks", json={"version_id": version_id})
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    poll = client.get(f"/compliance-jobs/{job_id}")
    assert poll.json()["result"]["blocked"] is True


def test_compliance_check_version_not_found(client):
    resp = client.post("/compliance-checks", json={"version_id": 9999})
    assert resp.status_code == 404


def test_job_not_found(client):
    resp = client.get("/compliance-jobs/nonexistent-id")
    assert resp.status_code == 404


# --- Helpers ---

class _FakeDim:
    def __init__(self, framework, code):
        self.framework = framework
        self.code = code
        self.name = code
        self.description = ""
        self.scoring_type = "Blocking" if framework == "REG" else "Advisory"
        self.weight = 1.0
        self.score_5_criteria = ""


def _fake_dim(framework, code):
    return _FakeDim(framework, code)
