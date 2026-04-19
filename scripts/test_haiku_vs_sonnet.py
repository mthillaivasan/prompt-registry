"""Pre-build test: Haiku vs Sonnet agreement for per-topic validation.

See docs/CHECKLIST_DESIGN.md §B5 and docs/BUILD_SESSION_A_BRIEF.md
for the protocol. Writes a markdown summary to
docs/HAIKU_VS_SONNET_RESULTS.md.

Run: `python -m scripts.test_haiku_vs_sonnet`
Requires: ANTHROPIC_API_KEY
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
HAIKU = "claude-haiku-4-5-20251001"

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "docs" / "HAIKU_VS_SONNET_RESULTS.md"


# ── Fixtures ─────────────────────────────────────────────────────────────────
# Three Extraction-brief scenarios at different completion states. Each lists
# the sibling context available to Claude and the focal topic being evaluated.

FIXTURES = [
    # Brief A — early stage, red-heavy
    {
        "brief_name": "A — early stage",
        "prompt_type": "Extraction",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
        },
        "topics": [
            ("topic_1_prompt_type", "Extraction"),
            ("topic_6_data_points", ""),
            ("topic_7_field_format", ""),
            ("topic_9_confidence_traceability", ""),
        ],
    },
    # Brief B — mid stage, amber mix
    {
        "brief_name": "B — mid stage",
        "prompt_type": "Extraction",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            "topic_3_output_format": "JSON object",
            "topic_4_target_system": "Simcorp",
            "topic_6_data_points": "subscription cut-off times",
        },
        "topics": [
            ("topic_1_prompt_type", "Extraction"),
            ("topic_6_data_points", "subscription cut-off times"),
            ("topic_7_field_format", "times as HH:MM"),
            ("topic_9_confidence_traceability", "Yes — page refs only"),
        ],
    },
    # Brief C — late stage, mostly green
    {
        "brief_name": "C — late stage",
        "prompt_type": "Extraction",
        "sibling_answers": {
            "topic_1_prompt_type": "Extraction",
            "topic_2_source_doc": "Prospectus",
            "topic_3_output_format": "JSON object",
            "topic_4_target_system": "Simcorp Dimension",
            "topic_5_risk_tier": "Limited",
            "topic_6_data_points": (
                "subscription cut-off time (HH:MM with timezone, found in Dealing Procedures), "
                "ISIN (ISO 6166 format, found in Share Class Details), "
                "minimum investment amount (float with currency code, found in Share Class Details)"
            ),
            "topic_8_null_handling": "null with confidence: low",
        },
        "topics": [
            ("topic_1_prompt_type", "Extraction"),
            ("topic_6_data_points", (
                "subscription cut-off time (HH:MM with timezone, found in Dealing Procedures), "
                "ISIN (ISO 6166 format, found in Share Class Details), "
                "minimum investment amount (float with currency code, found in Share Class Details)"
            )),
            ("topic_7_field_format", (
                "times normalised to UTC offset like +01:00. amounts as float. "
                "ISINs validated as 12-char alphanumeric."
            )),
            ("topic_9_confidence_traceability", "Yes — confidence + page/section ref per field"),
        ],
    },
]


def _build_user_message(topic_name: str, topic_answer: str, sibling_answers: dict[str, str]) -> str:
    if sibling_answers:
        sibling_block = "\n".join(f"- {k}: {v}" for k, v in sibling_answers.items())
    else:
        sibling_block = "None."
    answer_block = topic_answer if topic_answer else "(no answer yet)"
    return (
        f"FOCAL TOPIC ANSWER:\n{answer_block}\n\n"
        f"SIBLING ANSWERS FOR CONTEXT ONLY:\n{sibling_block}\n\n"
        f"PRIOR COACHING ON THIS TOPIC:\nNone."
    )


def _call(client: anthropic.Anthropic, model: str, system: str, user: str) -> tuple[dict, float]:
    t0 = time.monotonic()
    resp = client.messages.create(
        model=model, max_tokens=384, system=system,
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
    pairs = []

    for fx in FIXTURES:
        print(f"\n=== {fx['brief_name']} ===")
        for topic_id, topic_answer in fx["topics"]:
            system = build_validate_topic_system_prompt(fx["prompt_type"], topic_id)
            user = _build_user_message(topic_id, topic_answer, fx["sibling_answers"])
            print(f"  [{topic_id}] ...")
            try:
                sonnet_resp, sonnet_lat = _call(client, SONNET, system, user)
                haiku_resp, haiku_lat = _call(client, HAIKU, system, user)
            except Exception as e:
                print(f"    FAILED: {e}")
                pairs.append({
                    "brief": fx["brief_name"], "topic_id": topic_id,
                    "topic_answer": topic_answer,
                    "error": str(e),
                })
                continue
            pairs.append({
                "brief": fx["brief_name"],
                "topic_id": topic_id,
                "topic_answer": topic_answer,
                "sonnet": sonnet_resp,
                "sonnet_latency_s": round(sonnet_lat, 2),
                "haiku": haiku_resp,
                "haiku_latency_s": round(haiku_lat, 2),
                "state_agree": sonnet_resp.get("state") == haiku_resp.get("state"),
            })
            print(f"    sonnet={sonnet_resp.get('state')} ({sonnet_lat:.1f}s)  "
                  f"haiku={haiku_resp.get('state')} ({haiku_lat:.1f}s)  "
                  f"agree={pairs[-1]['state_agree']}")

    # Summary
    total = sum(1 for p in pairs if "sonnet" in p)
    agree = sum(1 for p in pairs if p.get("state_agree"))
    critical_disagree = [
        p for p in pairs if "sonnet" in p and not p["state_agree"]
        and {p["sonnet"].get("state"), p["haiku"].get("state")} == {"red", "green"}
    ]
    errors = [p for p in pairs if "error" in p]
    agree_rate = (agree / total) if total else 0.0

    if agree_rate >= 0.90 and not critical_disagree:
        recommendation = (
            f"**SHIP HAIKU.** State agreement {agree_rate:.0%} meets the ≥90% threshold, "
            "no red↔green disagreements."
        )
    elif critical_disagree:
        recommendation = (
            f"**SHIP SONNET.** {len(critical_disagree)} red↔green disagreement(s) — "
            "Haiku's classification drift is too wide to trust on material state boundaries."
        )
    else:
        recommendation = (
            f"**SHIP SONNET.** State agreement {agree_rate:.0%} below ≥90% threshold."
        )

    # Write markdown
    lines = [
        "# Haiku vs Sonnet — per-topic validate results",
        "",
        f"- Protocol: docs/CHECKLIST_DESIGN.md §B5",
        f"- Fixtures: {len(FIXTURES)} briefs × 4 topics each = {total} paired calls",
        f"- State-agreement rate: **{agree}/{total} = {agree_rate:.0%}**",
        f"- Red↔green disagreements: **{len(critical_disagree)}**",
        f"- Errors: **{len(errors)}**",
        "",
        f"## Recommendation",
        "",
        recommendation,
        "",
        "## Paired calls",
        "",
    ]
    for p in pairs:
        lines.append(f"### {p['brief']} · `{p['topic_id']}`")
        lines.append(f"- Answer: `{p['topic_answer'][:120] or '(empty)'}`")
        if "error" in p:
            lines.append(f"- **Error:** `{p['error']}`")
        else:
            lines.append(f"- **Sonnet** ({p['sonnet_latency_s']}s): `{json.dumps(p['sonnet'])[:300]}`")
            lines.append(f"- **Haiku** ({p['haiku_latency_s']}s): `{json.dumps(p['haiku'])[:300]}`")
            lines.append(f"- Agree on state: {'yes' if p['state_agree'] else 'NO'}")
        lines.append("")

    OUTPUT_PATH.write_text("\n".join(lines))
    print(f"\nWrote {OUTPUT_PATH}")
    print(f"Recommendation: {recommendation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
