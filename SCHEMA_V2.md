# SCHEMA_V2.md — Phase 2 schema design

**Block 6 deliverable.** Tables defined here are loaded by Block 7's
migration and seed. Each table is **generic** — no hard-coded rows, no
dimension-specific columns, no phase-specific columns. The four
invariants from Block 5 (Architecture note) apply throughout.

A reader of this file should be able to trace how a compliance run
resolves end to end without referring to specific dimensions or
standards.

---

## Design rules

1. **Configuration tables** (`standards`, `dimensions`, `phases`,
   `gates`, `applicability_rules`, `scoring_rubrics`, `form_fields`,
   `phase_weights`) are seeded from YAML. Schema admits any number
   of rows; engine code must work for an empty table.
2. **Record tables** (`prompts`, `prompt_versions`, `compliance_runs`,
   `deployment_records`, `operation_records`, `gate_decisions`,
   `audit_log`) are write-mostly. Records carry `phase_code` as a
   foreign key to `phases`, never a hard-coded enum in the model.
3. **Foreign keys** name the configuration row a record was scored
   against. A historical compliance run remains interpretable after a
   dimension is deactivated, because the run carries the dimension's
   identifier.
4. **No code branches on `phase_code` value.** Engine reads the
   row, applies the rules attached to that row, executes generically.

---

## Configuration tables

### `standards`

Holds the catalogue of external standards and regulations.

| Column | Type | Notes |
|---|---|---|
| standard_id | UUID PK | |
| standard_code | TEXT UNIQUE | e.g. `OWASP_LLM_TOP10` |
| title | TEXT | |
| version | TEXT | e.g. `2025`, `Regulation (EU) 2024/1689` |
| publisher | TEXT | |
| url | TEXT NULL | |
| notes | TEXT NULL | |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at | TEXT | ISO 8601 |
| updated_at | TEXT | |

Seeded from `seed/standards.yml`. Adding or revising a standard is a
config commit, not a code change.

### `phases`

Three rows: `build`, `deployment`, `operation`. Adding a fourth phase
(if a future regulator-imposed pre-Build assessment becomes required)
is a row insert.

| Column | Type | Notes |
|---|---|---|
| phase_id | UUID PK | |
| code | TEXT UNIQUE | `build` / `deployment` / `operation` |
| title | TEXT | |
| purpose | TEXT | |
| scoring_input | TEXT | `prompt_text` / `deployment_record` / `operation_record` |
| sort_order | INTEGER | |
| pass_threshold | NUMERIC | grade ≥ this is Pass |
| pass_with_warnings_threshold | NUMERIC | grade ≥ this is PWW |
| is_active | BOOLEAN DEFAULT TRUE | |

Engine code dispatches scoring inputs by `scoring_input` value, but
does not branch on `code`.

### `phase_weights`

Per-(phase, standard) composite weight. Replaces the legacy
hard-coded 40/30/20/10. A row of weight 0 excludes a standard from
the phase composite.

| Column | Type | Notes |
|---|---|---|
| phase_weight_id | UUID PK | |
| phase_id | UUID FK phases.phase_id | |
| standard_id | UUID FK standards.standard_id | |
| weight | NUMERIC | 0.0–1.0 |
| UNIQUE | (phase_id, standard_id) | |

### `dimensions`

The 16 (or future N) dimension records. The engine never references a
dimension by code; it loops over the table.

| Column | Type | Notes |
|---|---|---|
| dimension_id | UUID PK | |
| code | TEXT UNIQUE | seed identifier; appears in code only as data |
| title | TEXT | |
| phase_id | UUID FK phases.phase_id | |
| standard_id | UUID FK standards.standard_id | |
| clause | TEXT NULL | clause / subcategory reference |
| sort_order | INTEGER | display order |
| blocking_threshold | INTEGER DEFAULT 2 | score below blocks gate |
| is_mandatory | BOOLEAN | |
| scoring_type | TEXT | `Blocking` / `Advisory` / `Maturity` / `Alignment` |
| content_type | TEXT NULL | `prompt_content` / `wrapper_metadata` / `registry_policy` |
| applicability | TEXT (JSON) | structured rule, see grammar below |
| score_5_criteria | TEXT | |
| score_3_criteria | TEXT | |
| score_1_criteria | TEXT | |
| instructional_text | TEXT NULL | rendered into prompt body when content_type=prompt_content |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at | TEXT | |
| updated_at | TEXT | |

#### Applicability rule grammar

Stored as JSON in `dimensions.applicability`. Evaluated by a generic
service (`services.applicability.evaluate(rule, context)`) that does
not know dimension or phase identity.

```
{ "always": true }
{ "if_input_type_in": ["document", "PDF", "prospectus"] }
{ "if_risk_tier_at_least": "Limited" }
{ "if_prompt_type_in": ["Extraction", "Classification"] }
{ "all_of": [ rule, rule, ... ] }
{ "any_of": [ rule, rule, ... ] }
```

Adding a new rule shape is a code change to the evaluator (a small
generic function), not a per-dimension addition.

### `gates`

Approval rules per phase boundary. Three rows initially.

| Column | Type | Notes |
|---|---|---|
| gate_id | UUID PK | |
| code | TEXT UNIQUE | `build_to_deployment`, etc. |
| title | TEXT | |
| from_phase_id | UUID FK phases.phase_id | gates *out of* this phase |
| min_grade | NUMERIC | composite must meet this |
| approver_role | TEXT | `Maker` / `Checker` / `Admin` |
| rationale_required | BOOLEAN DEFAULT TRUE | |
| is_active | BOOLEAN DEFAULT TRUE | |

#### `gate_must_pass_dimensions`

Many-to-many. Lists the dimensions whose individual score must meet
the dimension's blocking threshold for the gate to pass, even if the
composite grade clears `min_grade`.

| Column | Type | Notes |
|---|---|---|
| gate_id | UUID FK gates.gate_id | |
| dimension_id | UUID FK dimensions.dimension_id | |
| PK | (gate_id, dimension_id) | |

### `form_fields`

Brief Builder, Deployment, and Operation form definitions. Driven by
`form_code` discriminator (e.g. `deployment_form`).

| Column | Type | Notes |
|---|---|---|
| field_id | UUID PK | |
| form_code | TEXT | `deployment_form`, `operation_review_form`, etc. |
| field_code | TEXT | unique within form |
| label | TEXT | |
| help_text | TEXT NULL | |
| field_type | TEXT | `text`, `select`, `multiselect`, `boolean`, `date`, `textarea` |
| options | TEXT (JSON) NULL | enum values for select types |
| validation | TEXT (JSON) NULL | required, min/max, regex |
| sort_order | INTEGER | |
| is_active | BOOLEAN DEFAULT TRUE | |
| UNIQUE | (form_code, field_code) | |

The Block 13 deployment form renders from this table. Adding a field
is a config commit; the form regenerates.

---

## Record tables

### `compliance_runs`

Replaces the existing `compliance_checks` shape. Carries `phase_id`,
which is the only structural change versus the legacy table.

| Column | Type | Notes |
|---|---|---|
| run_id | UUID PK | |
| phase_id | UUID FK phases.phase_id | which phase this run scored |
| subject_type | TEXT | `prompt_version` / `deployment_record` / `operation_record` |
| subject_id | UUID | FK is via subject_type — application-level |
| run_at | TEXT | |
| run_by | TEXT | user_id or `SYSTEM` |
| overall_result | TEXT NULL | `Pass` / `Pass with warnings` / `Fail` |
| composite_grade | NUMERIC NULL | weighted average |
| scores_json | TEXT (JSON) | per-dimension scores, frozen at run time |
| flags_json | TEXT (JSON) NULL | |

The `scores_json` array carries `dimension_id`, `dimension_code`
(snapshot), `score`, `rubric_match`, `flags`. Carrying the snapshot
of `dimension_code` lets the run remain readable even if a dimension
is later deactivated or renamed.

### `deployment_records`

Captures runtime context per deployed prompt version. Field set is
deliberately small — extensibility lives in `form_fields` plus a JSON
blob of form responses, not in column proliferation.

| Column | Type | Notes |
|---|---|---|
| deployment_id | UUID PK | |
| prompt_id | UUID FK prompts.prompt_id | |
| version_id | UUID FK prompt_versions.version_id | the version being deployed |
| invocation_context | TEXT | free-text summary; structured detail in form_responses |
| ai_platform | TEXT | from existing `prompts.ai_platform` migration |
| output_destination | TEXT | from existing `prompts.output_destination` migration |
| runtime_owner_id | UUID FK users.user_id | |
| form_responses_json | TEXT (JSON) | answers keyed by form_fields.field_code |
| status | TEXT | `Draft` / `Pending Approval` / `Approved` / `Rejected` / `Withdrawn` |
| created_at | TEXT | |
| updated_at | TEXT | |

### `operation_records`

Created when a deployment is approved.

| Column | Type | Notes |
|---|---|---|
| operation_id | UUID PK | |
| deployment_id | UUID FK deployment_records.deployment_id | |
| state | TEXT | `Active` / `Under Review` / `Suspended` / `Retired` |
| next_review_date | TEXT | computed from cadence config at creation |
| review_cadence_days | INTEGER | snapshot of cadence at deployment-approval time |
| incidents_json | TEXT (JSON) DEFAULT '[]' | append-only incident log |
| retired_at | TEXT NULL | |
| retired_reason | TEXT NULL | |
| created_at | TEXT | |
| updated_at | TEXT | |

### `gate_decisions`

One row per gate firing.

| Column | Type | Notes |
|---|---|---|
| decision_id | UUID PK | |
| gate_id | UUID FK gates.gate_id | |
| subject_type | TEXT | `prompt_version` / `deployment_record` |
| subject_id | UUID | |
| run_id | UUID FK compliance_runs.run_id | the run the gate evaluated |
| decision | TEXT | `Approved` / `Rejected` |
| decided_by | UUID FK users.user_id | |
| decided_at | TEXT | |
| rationale | TEXT NULL | required when `gates.rationale_required = TRUE` |

---

## Migration shape

Block 7 generates `migrations/002_phase2_schema.sql` to add these
tables. The legacy `scoring_dimensions` table is **not dropped**:
its data is migrated into the new `dimensions` table on first run,
and the legacy table is retained for one release cycle as a fallback
read-path. The legacy `compliance_checks` table is **not modified**;
new runs write to `compliance_runs` and the engine reads from both
during the transition.

This dual-write window lets Block 9 land its engine rewrite without
making the existing UI fail. A subsequent migration (post-Block 22)
drops the legacy tables.

The `phase_code` is added as a column on the existing
`compliance_checks` table by the migration so that Block 9's read
path can treat new and legacy runs uniformly.

The migration is reversible. A `migrations/002_phase2_schema_down.sql`
drops the new tables. Block 7 will smoke-test the down-migration
before treating the up-migration as committed.

---

## How a Build run resolves (worked example)

1. User submits prompt version V for compliance.
2. Engine resolves `phase_id` for `code='build'`.
3. Engine queries `dimensions WHERE phase_id = $build AND is_active`.
4. For each dimension D returned:
   a. Engine evaluates `D.applicability` against V's metadata.
   b. If applicable, engine renders the scoring rubric template with
      V.prompt_text and submits to the scoring model.
   c. Engine records `{dimension_id: D.id, code: D.code, score: ...}`
      into the run's `scores_json`.
5. Engine computes composite as the weighted average using
   `phase_weights` joined to standards.
6. Engine writes `compliance_runs` row with `phase_id=$build`.
7. Engine resolves the active gate for `from_phase_id=$build`.
8. Gate logic:
   - If `composite < min_grade` → result `Fail`, gate cannot fire.
   - For each dimension in `gate_must_pass_dimensions[gate]`:
     if `score < dim.blocking_threshold` → result `Fail`, gate
     cannot fire.
   - Otherwise the gate is **firable**; `gate_decisions` is written
     when an authorised user approves.

Step 4 is the only step that touches dimension specifics, and only
through generic JSON-driven rules. No `if dimension.code == X` exists
anywhere in the engine.

---

## What this schema does *not* introduce

- **No `Client` entity.** Per Block 1 finding F4, deferred to Phase 3.
  Client-scoped applicability rules can be retrofitted as another
  rule shape in the applicability grammar without schema change.
- **No deployment-form-fields-as-columns.** The `form_responses_json`
  blob plus the `form_fields` config table is the extensibility seam.
  Adding a field to the deployment form is a row insert in
  `form_fields`, not a column add.
- **No per-standard tables.** All standards live in one table; their
  clauses are stored as a string on the dimension row. A
  `standard_clauses` lookup table is a future refinement; absent for
  Phase 2 because the dimension table already carries the clause
  reference and adding a join in the UI buys little for the cost.

---

*End of SCHEMA_V2.md. Block 7 generates the migration from this spec.*
