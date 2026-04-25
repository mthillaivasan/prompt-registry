"""
Applicability + scoring helpers for the generic phase compliance engine.

Three pure functions that the engine composes. None reference dimension
codes, standard codes, or phase codes by name. They operate on:

  - rule:    a parsed JSON object from `dimensions.applicability`
  - context: a metadata dict (prompt_type, input_type, risk_tier, ...)
  - scores:  a {dimension_code: {"score": int, "rationale": str}} dict
  - dimensions: a sequence of objects with `code`, `standard_id`,
                `blocking_threshold` attributes
  - phase_weights: a {standard_id: float} dict

The engine reads its inputs from the database and passes them in. These
helpers are deliberately not coupled to the SQLAlchemy session — they
take primitives, return primitives, and are unit-testable without a DB.
"""

from typing import Any, Mapping, Sequence


# ── Risk tier ordering (the only quasi-hard-coded thing in this file) ────────
#
# Risk tier strings are values in the `prompts.risk_tier` CHECK constraint.
# Their ordering is a domain fact, not a dimension-specific value. If a future
# regulatory regime introduces a new tier, this list updates; nothing else.

_RISK_TIER_ORDER = ["Minimal", "Limited", "High", "Prohibited"]


def _tier_rank(tier: str | None) -> int:
    if tier is None:
        return -1
    try:
        return _RISK_TIER_ORDER.index(tier)
    except ValueError:
        return -1


# ── Rule evaluator ───────────────────────────────────────────────────────────

def evaluate(rule: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """Walk the applicability rule against the scoring context.

    Unknown rule shapes return False (fail-safe — a malformed rule excludes
    the dimension rather than including it implicitly).

    Supported shapes:
        {"always": true}
        {"if_input_type_in": ["document", ...]}
        {"if_prompt_type_in": ["Extraction", ...]}
        {"if_risk_tier_at_least": "Limited"}
        {"all_of": [rule, rule, ...]}
        {"any_of": [rule, rule, ...]}
        {"not": rule}

    The grammar is closed: adding a new rule type requires extending this
    function, which is a small generic change rather than per-dimension
    code.
    """
    if not isinstance(rule, Mapping):
        return False

    if rule.get("always") is True:
        return True

    if "if_input_type_in" in rule:
        return context.get("input_type") in rule["if_input_type_in"]

    if "if_prompt_type_in" in rule:
        return context.get("prompt_type") in rule["if_prompt_type_in"]

    if "if_risk_tier_at_least" in rule:
        floor = rule["if_risk_tier_at_least"]
        return _tier_rank(context.get("risk_tier")) >= _tier_rank(floor)

    if "all_of" in rule:
        clauses = rule["all_of"]
        return all(evaluate(c, context) for c in clauses)

    if "any_of" in rule:
        clauses = rule["any_of"]
        return any(evaluate(c, context) for c in clauses)

    if "not" in rule:
        return not evaluate(rule["not"], context)

    return False


# ── Composite grade ──────────────────────────────────────────────────────────

def composite_grade(
    scores: Mapping[str, Mapping[str, Any]],
    dimensions: Sequence[Any],
    phase_weights: Mapping[str, float],
) -> dict[str, Any]:
    """Compute the weighted composite grade.

    Each dimension's score (1-5) is normalised to 0-1, then weighted by its
    standard's weight in `phase_weights`, then averaged.

    `phase_weights` keys are standard_id values. Dimensions whose standard
    has weight 0 (or whose standard is absent from the weights map) do not
    contribute to the composite.

    Returns a dict shape compatible with the legacy `gold_standard` JSON so
    UI consumers do not need to change in this block. Block 10 reshapes.

    Stable behaviour: an empty dimension list yields a composite of 0.0.
    """
    if not dimensions:
        return {"composite": 0.0, "by_standard": {}, "scale": "0-100"}

    by_standard: dict[str, list[float]] = {}
    weight_by_standard: dict[str, float] = {}

    for d in dimensions:
        std_id = getattr(d, "standard_id", None)
        if std_id is None:
            continue
        entry = scores.get(d.code, {})
        raw_score = entry.get("score", 1) if isinstance(entry, Mapping) else 1
        try:
            raw_score = int(raw_score)
        except (TypeError, ValueError):
            raw_score = 1
        normalized = (raw_score - 1) / 4  # 1-5 → 0-1
        by_standard.setdefault(std_id, []).append(normalized)
        weight_by_standard[std_id] = float(phase_weights.get(std_id, 0.0))

    weighted_total = 0.0
    weight_sum = 0.0
    averages_by_standard: dict[str, float] = {}
    for std_id, normalized_scores in by_standard.items():
        avg = sum(normalized_scores) / len(normalized_scores)
        averages_by_standard[std_id] = round(avg * 4 + 1, 2)  # back to 1-5 for display
        weight = weight_by_standard.get(std_id, 0.0)
        weighted_total += avg * weight
        weight_sum += weight

    if weight_sum == 0:
        composite = 0.0
    else:
        composite = (weighted_total / weight_sum) * 100

    return {
        "composite": round(composite, 2),
        "by_standard": averages_by_standard,
        "scale": "0-100",
    }


# ── Gate evaluation ──────────────────────────────────────────────────────────

def gate_failed(
    scores: Mapping[str, Mapping[str, Any]],
    must_pass_dimension_codes: Sequence[str],
    dimensions: Sequence[Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Evaluate whether any must-pass dimension scored below its threshold.

    Returns (any_failed, list_of_failure_records).

    `must_pass_dimension_codes` is the list of dimension codes the gate
    requires to pass. The function looks up each in `dimensions` to find
    the threshold, then checks the score. A dimension code in the must-pass
    list that is absent from `dimensions` is skipped (the gate config
    references a deactivated dimension — log it elsewhere, do not block).
    """
    by_code = {d.code: d for d in dimensions}
    failures: list[dict[str, Any]] = []
    for code in must_pass_dimension_codes:
        d = by_code.get(code)
        if d is None:
            continue
        entry = scores.get(code, {})
        raw_score = entry.get("score", 1) if isinstance(entry, Mapping) else 1
        try:
            raw_score = int(raw_score)
        except (TypeError, ValueError):
            raw_score = 1
        threshold = getattr(d, "blocking_threshold", 2)
        if raw_score <= threshold:
            failures.append({
                "dimension_code": code,
                "dimension_title": getattr(d, "title", ""),
                "score": raw_score,
                "threshold": threshold,
                "rationale": entry.get("rationale", "") if isinstance(entry, Mapping) else "",
            })
    return (len(failures) > 0, failures)
