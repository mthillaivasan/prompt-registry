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

---

## 2026-04-25 — Block 21 — End-to-end smoke pass (synthetic)

**Setup.** `tests/test_block21_smoke.py` drives one prompt from Brief →
Build → Deployment → Operation against the live HTTP endpoints, with
Claude scoring stubbed out via the `score_provider` test seam.

The test passes. The interest is in what the test had to do that the
end user shouldn't have to.

### Friction surfaced

**F21.1 — There is no Build → Deployment gate endpoint.** Blocks 9 and
10 added Build phase compliance and standards labelling, but no router
endpoint fires the build gate. To approve a Build run, the smoke test
inserts a `gate_decisions` row directly via the DB session. A user
running the flow through the UI cannot do this — the dashboard's
`build_gate` marker therefore never lights up except for ad-hoc
backfills. Block 22 candidate (highest priority — without this, the
gate visibility on the dashboard is half-finished).

**F21.2 — Briefs need an explicit `/complete` endpoint to finalise.**
PATCH `/briefs/{id}` cannot transition status; only POST
`/briefs/{id}/complete` does. This is fine, but it's not discoverable
without reading the router source. A 422-style error from PATCH on
`status` would surface this faster. Minor.

**F21.3 — Linking a brief to its resulting prompt is a manual step.**
The smoke test does `Brief.resulting_prompt_id = prompt_id` directly
in SQL because no endpoint sets it. The intended flow is presumably
that `POST /prompts` linked to a brief should backfill, but it doesn't.
Without the link, the dashboard's Brief cell falls back to "Complete"
(legacy fallback), masking the issue. PHASE3 candidate or a quick
Block 22 fix.

**F21.4 — Dual-write of `prompts.ai_platform` happens at deployment
submit, but the `prompts.deployment_target` legacy column never moves.**
The deployment record's `model_provider` writes onto `ai_platform`, but
the prompt row's `deployment_target` is set at create-time and stays
stale. This is consistent with the spec ("transitional split") but a
user looking at the prompt row sees `deployment_target=OpenAI` even
when the deployment uses Anthropic. Resolved when the legacy column is
dropped (post-Block 22 cleanup is the named home for that).

**F21.5 — Audit log entries for deployment lifecycle use
`entity_type='PromptVersion'`.** The audit_log CHECK constraint does
not include `DeploymentRecord` or `OperationRecord`. The deployment
router uses 'PromptVersion' as the closest existing match. This is a
schema-level adjustment (CHECK widening) but pulls a migration,
parked. Phase 3 candidate.

**F21.6 — Operation `Approved` audit action is misleading on
rejection.** Block 16's gate uses action='DefectLogged' for rejections
(since 'Rejected' is not in the audit_log action CHECK). A rejected
deployment then appears in the audit timeline with the same action as
a logged compliance defect — confusing. The audit_log action enum
needs widening to add 'Rejected' and 'GateDecided'. Phase 3.

**F21.7 — Cadence resolution falls through to a Python constant.**
`services.operation_lifecycle._DEFAULT_REVIEW_CADENCE_DAYS = 90` is
the final fallback. Per the configuration-first principle this should
read from `phases.operation` — but the Phase row carries no cadence
column today. The fall-through is acceptable for v1 and called out in
OPERATION_SPEC §3, but the principle would prefer a row column.
Phase 3.

### What works smoothly

- **The dashboard ties the lifecycle together.** A row that walks Brief
  → Build → Deployment → Operation lights up correctly with the gate
  marker between Deployment and Operation. The lifecycle filter
  (`?lifecycle=at-operation`) returns only the prompts at that
  position, which is the test of "is the row position derivable from
  data alone".
- **Form responses dual-write to legacy columns** for `ai_platform` and
  `output_destination`, so the existing prompt-detail view sees an
  updated platform after submit.
- **The compliance engine is genuinely generic.** The same
  `run_phase_compliance` is called for Build, Deployment, and Operation
  in the smoke; each scores against rows tagged to its phase. No code
  branched on phase identity at any stage.
- **Standards labelling is consistent.** Each scored dimension across
  every phase carries `{standard_code, title, version, clause}` joined
  from the dimensions/standards tables. The UI never has to invent a
  label.

### Highest-priority fix candidate for Block 22

**F21.1** is the one to act on. Without a Build gate endpoint:

- The dashboard's `build_gate` marker never fires for any real-flow
  prompt.
- A Build-approved prompt cannot move to Deployment without a manual
  database write, breaking the only clean lifecycle path the spec
  defines.
- The audit log for Build approval is empty — there is no
  `gate_decisions` row to point at.

The fix is small and parallel to Block 16's existing deployment-gate
endpoint: a `POST /prompt-versions/{id}/build-gate-decision` on the
versions router, reading `gates WHERE from_phase_id=$build` and writing
a `gate_decisions` row. Block 22 should land this.

---

*Block 21 complete. Block 22 (highest-priority fix) follows — F21.1 is
the chosen fix.*
