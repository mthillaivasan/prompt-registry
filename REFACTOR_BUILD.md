# REFACTOR_BUILD.md — Build engine refactor brief

**Block 8 deliverable.** Specifies what changes in the Build compliance
engine, what the engine reads from configuration, and what tests must
be rewritten.

The Block 9 commit executes this brief.

---

## What the legacy engine hard-codes

`services/compliance_engine.py` has three hard-codings flagged by
Block 1 finding F1 and the BUILD_PROTOCOLS.md hard-coding table:

1. **`FRAMEWORK_WEIGHTS = {"REGULATORY": 0.40, ...}`** at lines 32–37.
   A standard catalogue rendered as a Python dict. **Reject.** Moves to
   `phase_weights` table seeded from `seed/standards.yml`.

2. **`count_blocking_defects` filters with `if d.framework != "REGULATORY":
   continue`** at line 175. Per-framework branch in code.
   **Reject.** Replaced with iteration over the gate's
   `must_pass_dimensions` set, queried from the database.

3. **Implicit phase = Build.** The engine has no concept of phase. Every
   call assumes Build because that is what the table contains. **Reject.**
   Engine is parameterised by `phase_code`; data tables hold the rest.

---

## What the new engine reads from configuration

| Behaviour | Source |
|---|---|
| Which dimensions apply | `dimensions` table where `phase_id = $build` and applicability rule evaluates true |
| Per-dimension scoring rubric | `dimensions.score_5_criteria` etc. |
| Per-dimension blocking threshold | `dimensions.blocking_threshold` |
| Per-(phase, standard) composite weight | `phase_weights` table |
| Pass / Pass-with-warnings / Fail thresholds | `phases.pass_threshold`, `phases.pass_with_warnings_threshold` |
| Which dimensions block the gate | `gate_must_pass_dimensions` joined to the gate whose `from_phase_id = $build` |

The engine signature becomes:

```python
def run_phase_compliance(
    db: Session,
    *,
    phase_code: str,                     # 'build' | 'deployment' | 'operation'
    subject_type: str,                   # 'prompt_version' | 'deployment_record' | 'operation_record'
    subject_id: str,
    run_by: str,
    scoring_input: dict,                 # phase-shaped dict; engine doesn't interpret
    metadata: dict | None = None,        # for applicability evaluation: prompt_type, input_type, risk_tier
) -> ComplianceRun
```

Notice: no Build-specific argument. The same function runs Deployment
in Block 15 with `phase_code='deployment'`. This is the test of the
configuration-first principle — one engine, three phases, no branches.

---

## Generic helpers

Three new pure-function helpers, all in `services/applicability.py`,
that the engine composes:

### `evaluate(rule, context) -> bool`

Walks the JSON applicability rule. Recursive for `all_of` and `any_of`.
Returns whether the dimension applies to this scoring run's context.
Unknown rule shapes return `False` (fail-safe).

### `composite_grade(scores, dimensions, phase_weights) -> float`

Replaces `compute_gold_standard`. Loops over scores, joins each to its
dimension's standard, looks up the (phase, standard) weight, normalises
to 0–1, weighted average, scaled to 0–100. Numerically identical to the
legacy code when the YAML preserves the legacy 40/30/20/10 weights.

### `gate_failed(scores, gate, dimensions) -> tuple[bool, list]`

Replaces the `if d.framework == "REGULATORY"` filter. Reads the gate's
`must_pass_dimensions`, looks up each in `scores`, returns whether any
fell below its `blocking_threshold` and the list of failures.

---

## What the legacy engine keeps

These do not violate the configuration-first principle and are kept:

- The two-call structure (scoring + anomaly detection)
- The cache invalidation on `prompt_versions.cache_valid`
- The async job lifecycle (`compliance_check_jobs`)
- The Anthropic client wrapper

The new engine writes to **both** `compliance_runs` (new) and
`compliance_checks` (legacy) during the transition. UI consumers
continue to read from `compliance_checks` until Block 10 flips them.

---

## Tests to rewrite

`tests/test_compliance.py` is the file most exposed to the rewrite.
The following patterns appear in tests and must be replaced:

| Test pattern | Replacement |
|---|---|
| Direct reference to `REG_D2` etc. as fixture data | Use `Dimension` row with synthetic code (`TEST_DIM_001`) seeded by the test |
| Assertion that `framework_averages["REGULATORY"]` equals X | Assert that the standard-grouped average equals X — query through the standards join, not a literal name |
| Assertion that blocking defects contain `OWASP_LLM01` | Assert that the dimension marked as `must_pass` for the gate is the one in the blocking list |
| Hard-coded composite weight 0.40 for REGULATORY | Read `phase_weights` and assert the composite computes against the seeded values |

A test that hard-codes a production dimension code is rewritten to
fixture-create its own dimensions. This is the test-side expression of
the configuration-first principle from `REFACTOR_PLAN.md` §5.

Tests in other files (`test_generation.py`, `test_prompts.py`,
`test_upgrade.py`, `test_brief_delete.py`, etc.) should continue to
pass without modification because they do not exercise the compliance
engine's internals.

The expected count of compliance-engine test rewrites is 15–30 per
the plan estimate. The engine rewrite must restore the suite to green
in the same commit.

---

## Out of scope for Block 9

- UI changes (Block 10 — grades name their standards)
- Smoke test (Block 11)
- Deployment phase (Block 15)
- Drop of legacy tables (post-Block 22)

Block 9 ships when:

- `services/compliance_engine.py` is generic per the signature above,
- `services/applicability.py` exists with the three helpers,
- The engine writes to `compliance_runs`,
- The engine still writes to `compliance_checks` for backward compat,
- Tests are green.

---

*End of brief.*
