"""Pre-build test: anti-drift rule holds in validate-topic system prompt.

See docs/CHECKLIST_DESIGN.md §B4 and docs/BUILD_SESSION_A_BRIEF.md.
Five fixture cases with deliberate sibling-topic gaps. Runs under
Sonnet (model test is in the companion script). Checks whether
Claude's probe stays focused on the focal topic or drifts into
probing the sibling gap.

Writes a markdown summary to docs/ANTI_DRIFT_TEST_RESULTS.md.

Drift heuristic (approximate — manual review the output too):
  - If Claude's `question` or `suggestion` mentions the sibling's
    gap term and doesn't mention the focal topic's subject, flag
    as DRIFT.
  - Otherwise flag as PASS.

Recommendation rule: drift > 10% (>= 1 of 5) → iterate phrasing
once and re-run. If still failing, ship with Sonnet and a note
that drift is a known residual risk.

Run: `python -m scripts.test_anti_drift`
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import anthropic

from services.topic_rubrics import build_validate_topic_system_prompt


SONNET = "claude-sonnet-4-20250514"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "ANTI_DRIFT_TEST_RESULTS.md"


CASES = [
    {
        "name": "1. focal=data_points (rich), sibling gap=output_format",
        "focal_topic": "topic_6_data_points",
        "focal_answer": (
            "subscription cut-off time (HH:MM with timezone, Dealing Procedures section), "
            "ISIN (ISO 6166, Share Class Details), minimum investment (float + currency, Share Class Details)"
        ),
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            # topic_3_output_format intentionally absent
        },
        "focal_subject_keywords": ["data", "field", "extract", "point"],
        "sibling_gap_keywords": ["output format", "output", "JSON", "table", "format of the output"],
    },
    {
        "name": "2. focal=field_format (answered), sibling gap=data_points",
        "focal_topic": "topic_7_field_format",
        "focal_answer": (
            "times normalised to UTC offset. amounts as float without currency symbol."
        ),
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            # topic_6_data_points intentionally absent
        },
        "focal_subject_keywords": ["format", "normalis", "per-field", "normaliz"],
        "sibling_gap_keywords": ["what fields", "which fields", "fields to extract", "data points"],
    },
    {
        "name": "3. focal=confidence_traceability (structured pick), sibling gap=risk_tier",
        "focal_topic": "topic_9_confidence_traceability",
        "focal_answer": "Yes — page refs only",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            "topic_6_data_points": "cut-off times, ISINs",
            # topic_5_risk_tier intentionally absent
        },
        "focal_subject_keywords": ["page ref", "granularity", "confidence", "traceab"],
        "sibling_gap_keywords": ["risk tier", "risk", "Minimal", "Limited", "High", "Prohibited"],
    },
    {
        "name": "4. focal=error_modes (answered briefly), sibling gap=target_system",
        "focal_topic": "topic_10_error_modes",
        "focal_answer": "partial document — skip the missing section and flag",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            "topic_6_data_points": "cut-off times, ISINs",
            # topic_4_target_system intentionally absent
        },
        "focal_subject_keywords": ["error", "exception", "partial", "malformed", "conflict"],
        "sibling_gap_keywords": ["target system", "where the output", "Simcorp", "Temenos"],
    },
    {
        "name": "5. focal=null_handling (preset pick), sibling gap=data_points",
        "focal_topic": "topic_8_null_handling",
        "focal_answer": "null with confidence: low",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            # topic_6_data_points intentionally absent
        },
        "focal_subject_keywords": ["null", "missing", "not found", "policy"],
        "sibling_gap_keywords": ["what fields", "which fields", "data point", "fields to extract"],
    },
]


def _build_user_message(topic_answer: str, sibling_answers: dict[str, str]) -> str:
    if sibling_answers:
        sibling_block = "\n".join(f"- {k}: {v}" for k, v in sibling_answers.items())
    else:
        sibling_block = "None."
    return (
        f"FOCAL TOPIC ANSWER:\n{topic_answer or '(no answer yet)'}\n\n"
        f"SIBLING ANSWERS FOR CONTEXT ONLY:\n{sibling_block}\n\n"
        f"PRIOR COACHING ON THIS TOPIC:\nNone."
    )


def _probe_text(resp: dict) -> str:
    """Flatten the parts of the response that could carry a probe."""
    parts = []
    for key in ("question", "suggestion", "suggested_addition"):
        val = resp.get(key)
        if isinstance(val, str):
            parts.append(val)
    options = resp.get("options") or []
    parts.extend(str(o) for o in options)
    return " | ".join(parts).lower()


def _classify(resp: dict, focal_kw: list[str], sibling_kw: list[str]) -> str:
    """DRIFT if probe mentions sibling gap but not focal subject. PASS otherwise."""
    if resp.get("state") == "green":
        return "PASS (state=green, no probe emitted)"
    text = _probe_text(resp)
    if not text:
        return "PASS (no probe content)"
    mentions_focal = any(k.lower() in text for k in focal_kw)
    mentions_sibling = any(k.lower() in text for k in sibling_kw)
    if mentions_sibling and not mentions_focal:
        return "DRIFT"
    if mentions_sibling and mentions_focal:
        return "MIXED (focal present but sibling also mentioned — manual review)"
    return "PASS"


def _call(client: anthropic.Anthropic, system: str, user: str) -> tuple[dict, float]:
    t0 = time.monotonic()
    resp = client.messages.create(
        model=SONNET, max_tokens=384, system=system,
        messages=[{"role": "user", "content": user}],
    )
    latency = time.monotonic() - t0
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"state": "parse_error", "raw": raw[:200]}
    return parsed, latency


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    client = anthropic.Anthropic()
    results = []

    for case in CASES:
        print(f"\n=== {case['name']} ===")
        system = build_validate_topic_system_prompt("Extraction", case["focal_topic"])
        user = _build_user_message(case["focal_answer"], case["sibling_answers"])
        try:
            resp, latency = _call(client, system, user)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({**case, "error": str(e)})
            continue
        classification = _classify(resp, case["focal_subject_keywords"], case["sibling_gap_keywords"])
        results.append({
            **case,
            "response": resp,
            "latency_s": round(latency, 2),
            "classification": classification,
        })
        print(f"  {classification}  (state={resp.get('state')}, {latency:.1f}s)")

    # Summary
    total = sum(1 for r in results if "error" not in r)
    drift = sum(1 for r in results if r.get("classification") == "DRIFT")
    mixed = sum(1 for r in results if r.get("classification", "").startswith("MIXED"))
    passed = sum(1 for r in results if r.get("classification", "").startswith("PASS"))
    errors = [r for r in results if "error" in r]
    drift_rate = (drift / total) if total else 0.0

    if drift == 0 and mixed == 0:
        recommendation = "**SHIP AS-IS.** Zero drift across all 5 cases; anti-drift rule holds."
    elif drift_rate <= 0.10:
        recommendation = (
            f"**SHIP AS-IS.** Drift {drift}/{total} = {drift_rate:.0%} ≤ 10%. "
            f"{mixed} mixed case(s) flagged for manual review."
        )
    else:
        recommendation = (
            f"**ITERATE PHRASING.** Drift {drift}/{total} = {drift_rate:.0%} > 10%. "
            "If iteration still fails, ship with Sonnet + residual-risk note."
        )

    lines = [
        "# Anti-drift rule — validate-topic results",
        "",
        f"- Protocol: docs/CHECKLIST_DESIGN.md §B4",
        f"- Fixtures: {len(CASES)} cases with deliberate sibling-topic gaps",
        f"- Model: {SONNET}",
        f"- PASS: **{passed}/{total}**",
        f"- MIXED (manual review): **{mixed}/{total}**",
        f"- DRIFT: **{drift}/{total} = {drift_rate:.0%}**",
        f"- Errors: **{len(errors)}**",
        "",
        "## Recommendation",
        "",
        recommendation,
        "",
        "## Case-by-case",
        "",
    ]
    for r in results:
        lines.append(f"### {r['name']}")
        lines.append(f"- Focal: `{r['focal_topic']}` — `{r['focal_answer'][:120]}`")
        lines.append(f"- Sibling gap: (absent from sibling_answers)")
        if "error" in r:
            lines.append(f"- **Error:** `{r['error']}`")
        else:
            lines.append(f"- Classification: **{r['classification']}**")
            lines.append(f"- State: `{r['response'].get('state')}` · Latency: {r['latency_s']}s")
            probe = _probe_text(r["response"]) or "(no probe)"
            lines.append(f"- Probe text: `{probe[:300]}`")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"Recommendation: {recommendation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
