# DEPLOYMENT_COMPLIANCE_SPEC.md — Block 14

The Deployment compliance engine is the **same code** as the Build
compliance engine. The generic engine introduced in Block 9 takes a
`phase_code`, fetches the dimensions tagged to that phase, evaluates each
dimension's applicability rule against the runtime metadata, runs the
applicable rubrics through the scoring model, aggregates per phase
weights, and writes a `compliance_runs` row.

This block is a specification, not new engine code. It confirms what is
reused, what is new, and what changes — and it pins the contract Block
15 will wire.

---

## 1. Reuse confirmation

The function `services.compliance_engine.run_phase_compliance(...)` is
already generic. It takes:

- `phase_code` — `'build' | 'deployment' | 'operation'`
- `subject_type` — `'prompt_version' | 'deployment_record' | 'operation_record'`
- `subject_id`
- `run_by`
- `scoring_input_text` — what the scoring model sees in `<INPUT>...</INPUT>`
- `metadata` — dict the applicability rules read from
- `score_provider` — optional injection point for tests / smoke

Block 15 calls this function with `phase_code='deployment'`. **No new
engine code is written.** A small `serialise_deployment_record(...)`
helper assembles the scoring text and metadata; that helper is the only
new function.

---

## 2. What changes — and what does not

### Unchanged

- `run_phase_compliance` — already generic across phases.
- The `dimensions`, `phases`, `phase_weights`, `gates`,
  `gate_must_pass_dimensions` schema — already designed to carry
  Deployment-tagged rows.
- `compliance_runs` — already carries `phase_id`, so a Deployment run
  is just a row with `phase_id = <deployment.phase_id>`.
- `services.applicability` — already supports the rule shapes the
  Deployment dimensions need (`if_input_type_in`, `if_risk_tier_at_least`,
  `all_of`, `any_of`, `not`).

### New

1. **A serialisation helper** —
   `services.deployment_compliance.serialise_deployment_record(db, record)`
   turns a `DeploymentRecord` into the pair `(scoring_input_text, metadata)`.
2. **An entry-point function** —
   `services.deployment_compliance.run_deployment_compliance(db, deployment_id, run_by)`
   that loads the record, calls the serialiser, dispatches to
   `run_phase_compliance`, and returns the run.
3. **A router endpoint** — `POST /deployments/{deployment_id}/compliance`
   triggers the run; `GET /deployments/{deployment_id}/compliance` returns
   the most recent run for that record.
4. **Seed work** — Deployment-phase dimensions need their rubric criteria
   filled in. Currently `seed/dimensions.yml` carries one Deployment row
   (`REG_OUTSOURCING_CONTROLS`). Block 14 adds Deployment-side dimensions
   for the OWASP and ISO checks the Block 12 form's fields drive
   (`OWASP_LLM01` runtime injection, `OWASP_LLM05` improper output
   handling, `OWASP_LLM10` unbounded consumption, `ISO42001_DATA_GOVERNANCE`
   runtime data flow). These are seed additions, not engine changes.

### Not introduced

- **No `if phase_code == 'deployment':` branch anywhere.** The engine
  has not learned the word "deployment" — it loops over rows tagged with
  the `phase_id` it was passed.
- **No deployment-specific scoring template.** The system prompt is
  rendered from `dimension.score_*_criteria` on whichever rows match.
- **No new aggregation logic.** Composite weighting and gate evaluation
  are inherited unchanged.
- **No new gate code.** Block 16 wires the existing gate primitive
  (`gate_must_pass_dimensions`, `min_grade`) to a Deployment-specific
  decision endpoint, but the gate evaluation itself is the same function.

---

## 3. Scoring input shape

For Build, `scoring_input_text` is the prompt text — a single string the
scoring model reads inside `<INPUT>…</INPUT>`. For Deployment, the input
is a structured view of the deployment record. The serialiser turns the
record into a deterministic, line-oriented representation so the scoring
model receives consistent shape across runs.

Format (newline-separated; field names normalised lower_snake_case):

```
PROMPT_TITLE: <prompts.title>
PROMPT_TYPE: <prompts.prompt_type>
PROMPT_RISK_TIER: <prompts.risk_tier>
PROMPT_VERSION: v<n>
PROMPT_TEXT:
<prompts.prompt_versions[active or selected].prompt_text>

DEPLOYMENT_INVOCATION_TRIGGER: <form_response>
DEPLOYMENT_INVOCATION_FREQUENCY_PER_DAY: <form_response>
DEPLOYMENT_LATENCY_ENVELOPE_SECONDS: <form_response>
DEPLOYMENT_INPUT_DATA_CATEGORIES: <comma-joined>
DEPLOYMENT_INPUT_REDACTION_APPLIED: <true|false>
DEPLOYMENT_INPUT_USER_SUPPLIED: <true|false>
DEPLOYMENT_OUTPUT_DESTINATION: <form_response>
DEPLOYMENT_OUTPUT_EXECUTED_BY_MACHINE: <true|false>
DEPLOYMENT_OUTPUT_STORAGE_RETENTION_DAYS: <form_response>
DEPLOYMENT_LOGGING_DESTINATION: <form_response>
DEPLOYMENT_METRIC_COLLECTION: <comma-joined>
DEPLOYMENT_ALERTING_THRESHOLDS_DEFINED: <true|false>
DEPLOYMENT_RUNTIME_OWNER_ID: <user_id>
DEPLOYMENT_APPROVER_ID: <user_id>
DEPLOYMENT_CHANGE_REVIEW_FREQUENCY_DAYS: <form_response>
DEPLOYMENT_BREAKING_CHANGE_PROTOCOL: <form_response>
DEPLOYMENT_MODEL_PROVIDER: <form_response>
DEPLOYMENT_DATA_RESIDENCY: <form_response>
DEPLOYMENT_SUB_PROCESSING_DISCLOSED: <true|false>
DEPLOYMENT_AUDIT_RIGHTS_IN_CONTRACT: <true|false>
```

The serialiser produces the keys for **whichever fields are present in
`form_responses_json`**. A field absent from responses is absent from the
output; the scoring model is told only what is true. New form fields
auto-appear in the serialised input on next deployment, no engine change
required — the serialiser walks the response dict.

The prompt text block is included so the scoring model has the artefact
context that the Build phase scored against. Build dimensions are
re-scored at Deployment-phase boundaries only if their applicability
rules say so (none currently do).

---

## 4. Applicability metadata

The `metadata` dict passed to `run_phase_compliance` is what the
applicability evaluator reads. For Deployment, the serialiser populates:

```
{
    "prompt_type":         <prompts.prompt_type>,
    "input_type":          <prompts.input_type>,
    "risk_tier":           <prompts.risk_tier>,
    "input_user_supplied": <bool, from form_responses>,
    "output_executed_by_machine": <bool, from form_responses>,
    "personal_data_present": <bool, derived from input_data_categories>,
}
```

Two of these (`input_user_supplied`, `output_executed_by_machine`,
`personal_data_present`) are Deployment-only — they don't exist for
Build. To support them, the applicability grammar adds two rule shapes
in Block 14:

```
{"if_flag_is_true":  "<flag_name>"}    # treats metadata[flag_name] as bool
{"if_flag_is_false": "<flag_name>"}
```

Adding these to `services.applicability.evaluate(...)` is a small
generic change — three lines of code, no per-dimension reference.

---

## 5. Dimension seed additions

Four Deployment-tagged dimensions are added to `seed/dimensions.yml`:

| Code | Standard | Applicability |
|---|---|---|
| OWASP_LLM01_RUNTIME | OWASP_LLM_TOP10 | `{"if_flag_is_true": "input_user_supplied"}` |
| OWASP_LLM05_OUTPUT_HANDLING | OWASP_LLM_TOP10 | `{"if_flag_is_true": "output_executed_by_machine"}` |
| OWASP_LLM10_UNBOUNDED | OWASP_LLM_TOP10 | `{"always": true}` |
| ISO42001_DATA_GOVERNANCE_RUNTIME | ISO_42001 | `{"if_flag_is_true": "personal_data_present"}` |

Each carries `phase: deployment`, a clause reference, and rubric
criteria pinned to the runtime concern (not the artefact concern). The
existing `REG_OUTSOURCING_CONTROLS` is already on the Deployment phase;
its scoring rubric is reviewed in this block to bind to the form's
`sub_processing_disclosed` / `audit_rights_in_contract` /
`data_residency` fields rather than a Build-style declaration.

The Deployment gate's `must_pass_dimensions` (currently
`REG_OUTSOURCING_CONTROLS`, `ISO42001_DATA_GOVERNANCE`) is updated to:

```
must_pass_dimensions:
  - REG_OUTSOURCING_CONTROLS
  - ISO42001_DATA_GOVERNANCE_RUNTIME
  - OWASP_LLM01_RUNTIME            # only blocks if applicable
  - OWASP_LLM05_OUTPUT_HANDLING    # only blocks if applicable
```

A dimension in the must-pass list whose applicability rule excludes it
from the run is silently skipped — already implemented at
`services/applicability.py` `gate_failed`. So the gate is correct
whether or not a given deployment has user-supplied input or
machine-acted output.

---

## 6. Block 15 contract

Block 15 implements:

1. `services/deployment_compliance.py` with two functions:
   - `serialise_deployment_record(db, record) -> (str, dict)`
   - `run_deployment_compliance(db, deployment_id, run_by, score_provider=None) -> ComplianceRun`
2. `POST /deployments/{deployment_id}/compliance` — kicks off a run.
3. `GET  /deployments/{deployment_id}/compliance` — fetches the latest run.
4. `services.applicability.evaluate` — extends grammar with
   `if_flag_is_true` / `if_flag_is_false`.
5. `seed/dimensions.yml` and `seed/gates.yml` — adds the four
   Deployment-tagged dimensions and updates the gate.
6. Tests — synthetic Deployment-phase fixture (no production codes) plus
   one round-trip test that loads the production seed and runs a
   deployment through with a stub scorer.

The four invariants from Block 5 are preserved:

1. No dimension is named in code outside seed loaders.
2. No phase is hard-coded on a dimension.
3. No standard reference is stored in code.
4. No gate rule is conditional on a specific dimension code.

---

## 7. What this spec rejects

- **A Deployment-specific scoring model prompt.** The system prompt is
  assembled from dimension rubrics; Deployment dimensions read the same
  way as Build dimensions to the model.
- **Per-field Python serialisers.** The serialiser walks
  `form_responses_json` keys generically, prefixing each with
  `DEPLOYMENT_`. Adding a form field is a YAML edit; the scoring text
  reflects it on the next run.
- **A separate engine for Deployment.** The pull to "make it its own
  module" is a configuration-first regression. One engine, one set of
  invariants, one shape across phases.
- **Storing the serialised text on the deployment record.** The text is
  computed at run time and lives in the run's audit context; the source
  of truth is `form_responses_json`. Storing the rendered string would
  duplicate state.

---

*Block 14 complete. Block 15 wires this spec.*
