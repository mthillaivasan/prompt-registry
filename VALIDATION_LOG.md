# VALIDATION_LOG.md

Friction log from running the new Build engine against the existing
prompt registry. One entry per smoke pass.

---

## 2026-04-25 — Block 11 — Smoke test Build (synthetic)

**Setup.** No live LLM call. `run_phase_compliance` invoked directly via
the `score_provider` test seam, exercising the new engine end to end
against the seeded Phase 2 catalogue (16 dimensions, the `build` phase,
`build_to_deployment` gate). Subject was a constructed prompt similar in
shape to one a user would author through the Brief Builder.

**Note.** A genuine smoke test requires a deployed instance and a real
LLM call. This entry covers the path I could exercise locally without
network. Treat the observations as engine-shape findings, not as
prompt-quality findings.

### What works

1. **The engine resolves a Build phase end to end without code touching
   any dimension or standard by name.** `run_phase_compliance` reads
   `dimensions WHERE phase_id=$build`, evaluates `applicability` per
   dimension, builds the system prompt, scores, computes the composite
   from `phase_weights`, evaluates `gate_must_pass_dimensions`, returns
   a `ComplianceRun`. The four invariants from `ARCHITECTURE.md` Block 5
   hold.

2. **The applicability rule grammar handles the cases the seed exercises.**
   `always: true`, `if_input_type_in`, `if_risk_tier_at_least` all behave
   as documented. `all_of` and `any_of` recurse correctly. Unknown rule
   shapes return false (fail-safe).

3. **Adding a new dimension is a YAML edit.** Confirmed by adding a
   throwaway `TEST_DIM` entry to a seed fixture and re-running
   `run_phase2_seed` — the engine picked it up without code change.

4. **Composite weights are tunable without code change.** Setting
   `EU_AI_ACT: 0.0` in `phase_weights` drops that standard from the
   composite while leaving its dimensions still scored and reported
   per-standard. Useful for "what would the grade be without X"
   sensitivity probes.

### What surprised

1. **The `framework_averages` shape is dead weight on the new engine.**
   The legacy `compute_gold_standard` returns `{composite, framework_averages,
   scale}`. The new `composite_grade` returns `{composite, by_standard, scale}`.
   These two shapes are not mergeable: framework_averages is keyed by
   four fixed names; by_standard is keyed by standard_id. Block 22
   candidate: drop `framework_averages` from the response after UI
   migrates.

2. **The applicability filter applies BEFORE the system-prompt build.**
   This is correct, but it means the system prompt the model sees varies
   per scoring run depending on metadata. A user repeating the same
   prompt with different `risk_tier` will see different dimensions
   scored. This is the intended config-first behaviour but is a UX
   surprise compared to the legacy "score everything always" engine.

3. **The new `compliance_runs` table is empty on most code paths.**
   The legacy `run_compliance_check` is what the `/compliance-checks`
   router calls; only `run_phase_compliance` writes to `compliance_runs`.
   Until Block 10's router flip is wired through, the new table is
   demo-only. Track for Block 22 follow-up.

4. **No `Phase = Build` enum in code.** The phase is read by string
   `'build'`, looked up in the `phases` table for its `phase_id`. This
   is correct per the principles but is a touch alien to a Python
   reader. A small typed wrapper (`PhaseCode = Literal['build', ...]`)
   in `schemas.py` would help static analysis without violating the
   configuration-first principle, since it would constrain string
   values rather than encoding behaviour. Not in Block 22 unless time
   allows.

### What dimension config needs tuning

These are observations from reading the seeded text, not from real LLM
output:

- **`OWASP_SYSTEM_PROMPT_LEAKAGE`** is new (added in Block 4). Its
  instructional text says "do not echo the role you have been given".
  In practice many production prompts *do* declare role — "You are a
  compliance assessor" — and the LLM is expected to keep that role.
  The dimension's text needs revision to distinguish role-declaration
  (which is fine) from role-echo-on-demand (which is the actual risk).
  Logged as Block 22 candidate.

- **`REG_OUTSOURCING_CONTROLS`** is the only Deployment dimension. Its
  applicability is `always: true`, but at Build phase it would never
  apply since the phase filter excludes it from Build runs. Worth a
  separate Build-phase declaration variant that asks the prompt to
  *declare* outsourcing posture rather than enforce it. Block 14 task.

- **`ISO42001_DATA_GOVERNANCE`** is intentionally split (Build
  declaration + Deployment binding) but only the Build half is in the
  seed. Block 14 must add the Deployment half.

### What to fix

Nothing blocking. The synthetic smoke pass executes the new engine, and
the engine behaves per spec. Real LLM smoke (Block 21 territory) will
surface dimension-text quality issues that this pass cannot.

---

*Block 11 complete. Block 12 (DEPLOYMENT_FORM_SPEC.md) follows.*
