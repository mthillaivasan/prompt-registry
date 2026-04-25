"""
Tests for the Phase 2 generic compliance engine.

Per REFACTOR_BUILD.md, these tests use synthetic dimensions seeded as
fixtures rather than referencing production dimension codes. A test that
hard-codes a production code (e.g. "OWASP_PROMPT_INJECTION") is a
regression — synthetic codes (TEST_DIM_*) prove the engine is generic.
"""

import json

import pytest

from app.database import SessionLocal
from app.models import (
    Dimension,
    Gate,
    GateMustPassDimension,
    Phase,
    PhaseWeight,
    Standard,
)
from services import applicability
from services.compliance_engine import (
    build_phase_system_prompt,
    get_must_pass_codes,
    get_phase_dimensions,
    get_phase_weights,
    run_phase_compliance,
)


# ── Fixture helpers — synthetic dimensions, no production codes ─────────────

@pytest.fixture
def synthetic_phase(db):
    """Create a synthetic phase, standards, dimensions, and gate.

    All identifiers are TEST_* so the engine cannot accidentally match
    against production seed data.
    """
    # Two synthetic standards
    s1 = Standard(
        standard_code="TEST_STD_ALPHA",
        title="Test standard alpha",
        version="1",
        publisher="Test",
    )
    s2 = Standard(
        standard_code="TEST_STD_BETA",
        title="Test standard beta",
        version="1",
        publisher="Test",
    )
    db.add_all([s1, s2])
    db.flush()

    p = Phase(
        code="test_phase",
        title="Test phase",
        purpose="For tests",
        scoring_input="prompt_text",
        sort_order=99,
    )
    db.add(p)
    db.flush()

    # Weights: alpha gets 0.7, beta gets 0.3
    db.add_all([
        PhaseWeight(phase_id=p.phase_id, standard_id=s1.standard_id, weight="0.7"),
        PhaseWeight(phase_id=p.phase_id, standard_id=s2.standard_id, weight="0.3"),
    ])

    # Three dimensions: alpha-1 must-pass, alpha-2 advisory, beta-1 advisory
    dims = [
        Dimension(
            code="TEST_DIM_ALPHA_1",
            title="Alpha 1",
            phase_id=p.phase_id,
            standard_id=s1.standard_id,
            sort_order=1,
            blocking_threshold=2,
            is_mandatory=True,
            scoring_type="Blocking",
            applicability='{"always": true}',
            score_5_criteria="all good",
            score_3_criteria="ok",
            score_1_criteria="bad",
        ),
        Dimension(
            code="TEST_DIM_ALPHA_2",
            title="Alpha 2",
            phase_id=p.phase_id,
            standard_id=s1.standard_id,
            sort_order=2,
            blocking_threshold=2,
            is_mandatory=False,
            scoring_type="Advisory",
            applicability='{"always": true}',
            score_5_criteria="all good",
            score_3_criteria="ok",
            score_1_criteria="bad",
        ),
        Dimension(
            code="TEST_DIM_BETA_1",
            title="Beta 1",
            phase_id=p.phase_id,
            standard_id=s2.standard_id,
            sort_order=3,
            blocking_threshold=2,
            is_mandatory=False,
            scoring_type="Advisory",
            applicability='{"if_input_type_in": ["document"]}',
            score_5_criteria="all good",
            score_3_criteria="ok",
            score_1_criteria="bad",
        ),
    ]
    db.add_all(dims)
    db.flush()

    # Gate: alpha-1 must pass
    g = Gate(
        code="test_gate",
        title="Test gate",
        from_phase_id=p.phase_id,
        min_grade="3.0",
        approver_role="Checker",
    )
    db.add(g)
    db.flush()
    db.add(GateMustPassDimension(gate_id=g.gate_id, dimension_id=dims[0].dimension_id))

    db.commit()
    return {
        "phase_code": "test_phase",
        "phase_id": p.phase_id,
        "standard_alpha": s1.standard_id,
        "standard_beta": s2.standard_id,
        "dim_alpha_1": dims[0].dimension_id,
        "dim_alpha_2": dims[1].dimension_id,
        "dim_beta_1": dims[2].dimension_id,
    }


# ── Applicability helpers — pure unit tests ─────────────────────────────────

def test_applicability_always():
    assert applicability.evaluate({"always": True}, {}) is True


def test_applicability_input_type():
    rule = {"if_input_type_in": ["document", "PDF"]}
    assert applicability.evaluate(rule, {"input_type": "document"}) is True
    assert applicability.evaluate(rule, {"input_type": "plain text"}) is False


def test_applicability_risk_tier():
    rule = {"if_risk_tier_at_least": "Limited"}
    assert applicability.evaluate(rule, {"risk_tier": "Minimal"}) is False
    assert applicability.evaluate(rule, {"risk_tier": "Limited"}) is True
    assert applicability.evaluate(rule, {"risk_tier": "High"}) is True


def test_applicability_all_of():
    rule = {
        "all_of": [
            {"if_input_type_in": ["document"]},
            {"if_risk_tier_at_least": "Limited"},
        ]
    }
    assert applicability.evaluate(rule, {"input_type": "document", "risk_tier": "High"}) is True
    assert applicability.evaluate(rule, {"input_type": "document", "risk_tier": "Minimal"}) is False
    assert applicability.evaluate(rule, {"input_type": "plain text", "risk_tier": "High"}) is False


def test_applicability_any_of():
    rule = {
        "any_of": [
            {"if_input_type_in": ["document"]},
            {"if_risk_tier_at_least": "High"},
        ]
    }
    assert applicability.evaluate(rule, {"input_type": "document", "risk_tier": "Minimal"}) is True
    assert applicability.evaluate(rule, {"input_type": "plain", "risk_tier": "High"}) is True
    assert applicability.evaluate(rule, {"input_type": "plain", "risk_tier": "Limited"}) is False


def test_applicability_unknown_rule_is_false():
    # Fail-safe: unrecognised rule shape excludes the dimension.
    assert applicability.evaluate({"weird_thing": True}, {}) is False


# ── Composite grade ──────────────────────────────────────────────────────────

class _SyntheticDim:
    def __init__(self, code, standard_id, blocking_threshold=2, title=""):
        self.code = code
        self.standard_id = standard_id
        self.blocking_threshold = blocking_threshold
        self.title = title


def test_composite_all_fives():
    dims = [_SyntheticDim("A", "s1"), _SyntheticDim("B", "s2")]
    scores = {"A": {"score": 5}, "B": {"score": 5}}
    weights = {"s1": 0.5, "s2": 0.5}
    g = applicability.composite_grade(scores, dims, weights)
    assert g["composite"] == 100.0


def test_composite_all_ones():
    dims = [_SyntheticDim("A", "s1")]
    scores = {"A": {"score": 1}}
    weights = {"s1": 1.0}
    g = applicability.composite_grade(scores, dims, weights)
    assert g["composite"] == 0.0


def test_composite_zero_weight_excluded():
    """A dimension whose standard has weight 0 contributes to by_standard
    but not to composite."""
    dims = [_SyntheticDim("A", "s1"), _SyntheticDim("B", "s2")]
    scores = {"A": {"score": 5}, "B": {"score": 1}}
    weights = {"s1": 1.0, "s2": 0.0}
    g = applicability.composite_grade(scores, dims, weights)
    # Only s1 contributes — score 5 → composite 100
    assert g["composite"] == 100.0


# ── Gate evaluation ──────────────────────────────────────────────────────────

def test_gate_failed_when_must_pass_below_threshold():
    dims = [_SyntheticDim("A", "s1", blocking_threshold=3, title="Alpha")]
    scores = {"A": {"score": 2, "rationale": "weak"}}
    failed, details = applicability.gate_failed(scores, ["A"], dims)
    assert failed is True
    assert len(details) == 1
    assert details[0]["dimension_code"] == "A"
    assert details[0]["score"] == 2
    assert details[0]["threshold"] == 3


def test_gate_passes_when_must_pass_at_threshold():
    dims = [_SyntheticDim("A", "s1", blocking_threshold=2)]
    scores = {"A": {"score": 3}}
    failed, details = applicability.gate_failed(scores, ["A"], dims)
    assert failed is False
    assert details == []


def test_gate_skips_must_pass_codes_not_in_dimensions():
    """A code in must-pass list but absent from dimensions is silently
    skipped (deactivated dimension)."""
    dims = [_SyntheticDim("A", "s1")]
    failed, details = applicability.gate_failed({"A": {"score": 5}}, ["A", "GHOST"], dims)
    assert failed is False


# ── Generic engine end-to-end ────────────────────────────────────────────────

def test_get_phase_dimensions_returns_active(db, synthetic_phase):
    dims = get_phase_dimensions(db, "test_phase")
    assert len(dims) == 3
    codes = {d.code for d in dims}
    assert codes == {"TEST_DIM_ALPHA_1", "TEST_DIM_ALPHA_2", "TEST_DIM_BETA_1"}


def test_get_phase_weights_returns_seeded(db, synthetic_phase):
    weights = get_phase_weights(db, "test_phase")
    # Sum is 1.0; specific values 0.7 + 0.3
    assert round(sum(weights.values()), 2) == 1.0
    assert sorted(weights.values()) == [0.3, 0.7]


def test_get_must_pass_codes_returns_gate_dims(db, synthetic_phase):
    from services.compliance_engine import get_gate_for_phase
    gate = get_gate_for_phase(db, "test_phase")
    codes = get_must_pass_codes(db, gate)
    assert codes == ["TEST_DIM_ALPHA_1"]


def test_phase_system_prompt_no_dimension_codes_hardcoded(db, synthetic_phase):
    dims = get_phase_dimensions(db, "test_phase")
    prompt = build_phase_system_prompt(dims)
    # The prompt should contain whatever codes config has — no hard-coded names.
    assert "TEST_DIM_ALPHA_1" in prompt
    assert "{scoring_input}" in prompt
    # Negative: production codes must NOT appear since they aren't in this phase.
    assert "REG_REGULATORY_FRAMEWORK" not in prompt
    assert "OWASP_PROMPT_INJECTION" not in prompt


def test_run_phase_compliance_pass(db, synthetic_phase):
    """All scores at 5: composite 100, gate passes, overall Pass."""
    def fake_score(system_prompt, user_message):
        return json.dumps({"scores": {
            "TEST_DIM_ALPHA_1": {"score": 5, "rationale": "good"},
            "TEST_DIM_ALPHA_2": {"score": 5, "rationale": "good"},
        }})

    run = run_phase_compliance(
        db,
        phase_code="test_phase",
        subject_type="prompt_version",
        subject_id="00000000-0000-0000-0000-000000000001",
        run_by="SYSTEM",
        scoring_input_text="dummy input",
        metadata={"input_type": "plain"},  # excludes BETA_1
        score_provider=fake_score,
    )
    assert run.overall_result == "Pass"
    assert float(run.composite_grade) == 100.0


def test_run_phase_compliance_fails_on_must_pass(db, synthetic_phase):
    """ALPHA_1 scores 1; gate must-pass fails -> overall Fail."""
    def fake_score(system_prompt, user_message):
        return json.dumps({"scores": {
            "TEST_DIM_ALPHA_1": {"score": 1, "rationale": "bad"},
            "TEST_DIM_ALPHA_2": {"score": 5, "rationale": "good"},
        }})

    run = run_phase_compliance(
        db,
        phase_code="test_phase",
        subject_type="prompt_version",
        subject_id="00000000-0000-0000-0000-000000000002",
        run_by="SYSTEM",
        scoring_input_text="dummy",
        metadata={"input_type": "plain"},
        score_provider=fake_score,
    )
    assert run.overall_result == "Fail"
    flags = json.loads(run.flags_json)
    assert flags[0]["type"] == "gate_failures"
    assert flags[0]["details"][0]["dimension_code"] == "TEST_DIM_ALPHA_1"


def test_applicability_filters_dimensions(db, synthetic_phase):
    """BETA_1 has rule if_input_type_in=document; should apply only when
    metadata says input_type=document."""
    seen_codes = []

    def fake_score(system_prompt, user_message):
        # The system prompt lists only the applicable dimensions.
        # Capture them for assertion.
        for code in ["TEST_DIM_ALPHA_1", "TEST_DIM_ALPHA_2", "TEST_DIM_BETA_1"]:
            if code in system_prompt:
                seen_codes.append(code)
        return json.dumps({"scores": {
            code: {"score": 5, "rationale": "ok"} for code in seen_codes
        }})

    # Without document context -> BETA_1 excluded
    seen_codes.clear()
    run_phase_compliance(
        db,
        phase_code="test_phase",
        subject_type="prompt_version",
        subject_id="00000000-0000-0000-0000-000000000003",
        run_by="SYSTEM",
        scoring_input_text="x",
        metadata={"input_type": "plain"},
        score_provider=fake_score,
    )
    assert "TEST_DIM_BETA_1" not in seen_codes
    assert "TEST_DIM_ALPHA_1" in seen_codes

    # With document context -> BETA_1 included
    seen_codes.clear()
    run_phase_compliance(
        db,
        phase_code="test_phase",
        subject_type="prompt_version",
        subject_id="00000000-0000-0000-0000-000000000004",
        run_by="SYSTEM",
        scoring_input_text="x",
        metadata={"input_type": "document"},
        score_provider=fake_score,
    )
    assert "TEST_DIM_BETA_1" in seen_codes


def test_engine_does_not_branch_on_phase_code(db, synthetic_phase):
    """Smoke test: pointing the engine at the synthetic phase produces a
    valid run, proving the engine code doesn't branch on phase identity.
    The same call shape would work for build / deployment / operation —
    the engine just reads the rows tagged with the given phase_code."""
    def fake_score(*_):
        return json.dumps({"scores": {
            "TEST_DIM_ALPHA_1": {"score": 5, "rationale": "ok"},
            "TEST_DIM_ALPHA_2": {"score": 4, "rationale": "ok"},
        }})

    run = run_phase_compliance(
        db,
        phase_code="test_phase",
        subject_type="prompt_version",
        subject_id="00000000-0000-0000-0000-000000000005",
        run_by="SYSTEM",
        scoring_input_text="x",
        metadata={"input_type": "plain"},
        score_provider=fake_score,
    )
    assert run.run_id is not None
    assert run.overall_result in ("Pass", "Pass with warnings", "Fail")
