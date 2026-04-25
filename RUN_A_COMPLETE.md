# RUN_A_COMPLETE.md

Summary of the autonomous Run A continuation. The previous session
landed Blocks 1-11; this one ran from Block 12 through Block 22 plus
the closing summary. All work on branch `run-a`. Tests stay green
across every block (242 → 254 → 264 final).

---

## What landed, by block

### Block 12 — Deployment form spec (committed e8e09b5)

Existing untracked `DEPLOYMENT_FORM_SPEC.md` and `seed/form_fields.yml`
from the interrupted session were reviewed and committed unchanged.
Both aligned with the Block 6 schema and Block 5 architecture. The
seed loader (`app/seed_phase2.py`) already had `form_fields` support
from Block 7, so the YAML loaded cleanly into 21 deployment_form
fields.

### Block 13 — Deployment form build (committed b06133b)

Config-driven endpoints:

- `GET /forms/{form_code}` — field definitions for the renderer.
- `POST /deployments` — create Draft record.
- `PUT /deployments/{id}` — save responses with non-blocking validation.
- `POST /deployments/{id}/submit` — enforce validation, transition to
  Pending Approval, dual-write `ai_platform` / `output_destination`
  onto the prompt row.

`services/form_validation.py` is generic — loops over FormField rows,
applies the JSON validation grammar (required, pattern, in, min/max),
returns errors keyed by field_code. No per-field Python validators.

Owner / approver `select` fields ship with empty `options[]` in seed
and are populated server-side from the users table at config-fetch.

Bug fix: the seed file's `latency_envelope_seconds` pattern was
double-escaped (`'\\.'` in single-quoted YAML reads as a literal
backslash-period). Fixed.

17 new tests.

### Block 14 — Deployment compliance engine spec (committed 49738b7)

`DEPLOYMENT_COMPLIANCE_SPEC.md` confirmed the Block 9 generic engine
is reused for Deployment unchanged. The only new code in Block 15
would be: a serialiser, two grammar additions to `applicability`
(`if_flag_is_true` / `if_flag_is_false`), and four Deployment-tagged
seed dimensions. The four invariants from Block 5 stay intact.

### Block 15 — Deployment compliance build (committed d83fc11)

`services/deployment_compliance.py` — serialiser, run dispatch, latest-
run fetch. Added `if_flag_is_true` / `if_flag_is_false` to
`services/applicability.py`. Added four Deployment-tagged dimensions
in `seed/dimensions.yml`:

| Code | Standard | Applicability |
|---|---|---|
| OWASP_LLM01_RUNTIME | OWASP LLM Top 10 | input_user_supplied=true |
| OWASP_LLM05_OUTPUT_HANDLING | OWASP LLM Top 10 | output_executed_by_machine=true |
| OWASP_LLM10_UNBOUNDED | OWASP LLM Top 10 | always |
| ISO42001_DATA_GOVERNANCE_RUNTIME | ISO 42001 | personal_data_present=true |

Updated `seed/gates.yml` so the Deployment gate's must-pass list
covers the four runtime safety floors. Added router endpoints
`POST /deployments/{id}/compliance` and `GET /deployments/{id}/compliance`
with standards labelling joined per scored dimension.

Engine itself unchanged. No `if phase_code == 'deployment'` branch
anywhere. 9 new tests.

### Block 16 — Deployment gate (committed 1c304a1)

`POST /deployments/{id}/gate-decision` and
`GET /deployments/{id}/gate-decisions`. Reads from `gates` config
(approver_role and rationale_required). A small `_role_satisfies`
helper enforces the role hierarchy (Maker < Checker < Admin).
Cannot approve a deployment whose latest ComplianceRun is
`overall_result='Fail'`. 10 new tests.

### Block 17 — Operation spec (committed e4e36ee)

`OPERATION_SPEC.md`. Defined the lifecycle (Active / Under Review /
Suspended / Retired), config-driven cadence (form response → phase
default → 90), severity-driven incident → state transitions, and a
retirement-trigger schema. Planned two new dimensions
(NIST_MEASURE_RUNTIME, NIST_MANAGE_DECOMMISSION_RUNTIME). Auto-retire
parked because retire is irreversible state.

### Block 18 — Operation build (committed ee9fe5d)

`services/operation_lifecycle.py` (auto-creation, cadence resolution,
incidents with severity-driven state flip, serialiser, run dispatch
with state transitions). `app/routers/operations.py` exposing list /
get / run / runs / incidents / retire / return-to-active. The
deployment gate's Approved branch creates the operation record
idempotently. Added the two Operation-tagged dimensions in
`seed/dimensions.yml`. 13 new tests.

### Block 19 — Dashboard redesign spec (committed a003222)

`DASHBOARD_SPEC.md`. Four columns (Brief, Build, Deployment,
Operation), one row per prompt, finite cell vocabulary with
state→colour mapping, gate markers between columns. Single endpoint
contract `GET /dashboard`.

### Block 20 — Dashboard build (committed 0fde401)

`services/dashboard_view.py` assembles row data; cell vocabulary lives
as data, not as phase branches. `app/routers/dashboard.py` exposes the
filterable endpoint. Updated `static/views/dashboard.js` to render the
four-phase row layout with inline gate markers. 12 new tests.

### Block 21 — End-to-end smoke (committed 8b37c89)

`tests/test_block21_smoke.py` drives one prompt through the full
lifecycle against the live HTTP endpoints with the Claude scorer
stubbed. Surfaced seven findings (F21.1 - F21.7) recorded in
`VALIDATION_LOG.md`.

### Block 22 — Highest-priority fix + PHASE3 (committed 0a1a448)

F21.1 (no Build → Deployment gate endpoint) was the only flow-blocking
finding. Added `app/routers/build_gate.py` symmetric with the Block 16
deployment gate. The dashboard's `build_gate` marker now lights up on
real flow. 9 new tests. Created `PHASE3.md` cataloguing every parked
item from Blocks 11, 14, 17, 21 plus cross-cutting cleanups.

---

## Decisions made

These choices weren't dictated by the plan and went one way rather
than another. Listed because future readers should know they were
decisions, not defaults.

1. **Build the API and skip the JS-form UI for Block 13.** The plan's
   done state was "form is live and writes to deployment_records, fields
   rendered from config". The endpoints satisfy this. A JS form UI
   would have added scope I couldn't test in a browser this session.
   Block 20 reused the existing dashboard JS so the user has a live
   read surface; the deployment-form write surface is API-only for
   now. Captured for PHASE3 if it bites.

2. **Serialise the deployment record by walking the response dict
   generically rather than cherry-picking fields.** The serialiser
   prefixes every response key with `DEPLOYMENT_<FIELD>:`. Adding a
   form field is a YAML edit; the scoring text reflects it on the
   next run, no engine change. This was the configuration-first read
   of "scoring input is the deployment record".

3. **Auto-create operation_record on gate Approved (not on a separate
   endpoint).** The plan's Block 18 done state is "every deployed
   prompt has a live Operation entry". The hook fires from inside the
   deployment gate handler. Idempotent so a re-fire is safe. There is
   no public POST /operation endpoint.

4. **Reject auto-retire.** OPERATION_SPEC explicitly rules it out —
   retirement is a Checker decision; rules *recommend*. This is one
   block-internal call (Block 17 spec); flagging here because it
   shifts what "retirement triggers" means in the architecture.

5. **Keep the legacy `prompts.deployment_target` write at create time.**
   Per F21.4 the column is stale relative to deployment.ai_platform
   after submit. The plan calls this out as a transitional split that
   resolves post-Block 22 cleanup. Did not chase.

6. **Use `entity_type='PromptVersion'` for deployment / operation
   audit entries.** The audit_log CHECK constraint has no
   `'DeploymentRecord'` or `'OperationRecord'` enum value. Widening it
   is a schema migration that pulls into Block 22's scope; parked at
   F21.5 in PHASE3.md.

7. **Skip retirement_triggers table for Block 18.** OPERATION_SPEC §3
   defined the seed schema; Block 18 did not implement it. Without a
   scheduler, the only consumer of trigger rules would be manual
   cadence-runs, which already produce a compliance run that exposes
   the same signal differently. Not worth a table for v1. PHASE3.md.

8. **Block 22 fix scope limited to F21.1.** The plan says "one fix
   only". F21.1 was the only flow-blocking finding (the others are
   discoverability or audit fidelity). Six remaining findings
   parked in PHASE3.md with reasoning.

---

## What surprised

1. **The applicability grammar paid off immediately.** Adding
   `if_flag_is_true` / `if_flag_is_false` was three lines in
   `services/applicability.py` and unblocked the entire Deployment
   dimension set. The `gate_failed` function already handled
   "applicable list ≠ must-pass list" silently, so the Deployment
   gate works when `OWASP_LLM05_OUTPUT_HANDLING` is excluded by its
   applicability rule. The Block 5 invariant ("no gate rule conditional
   on a specific dimension code") and the Block 15 work landed
   together cleanly because of this.

2. **The legacy Build path is still the routed entry for compliance.**
   `/compliance-checks` calls the legacy `run_compliance_check` (which
   delegates to the engine but dual-writes to the legacy table). The
   new Phase 2 path (`run_phase_compliance` writing to `compliance_runs`)
   is exercised by Deployment, Operation, and the Block 21 smoke, but
   it is *not* what the Build router calls. The dashboard handles this
   by reading both tables — `compliance_runs` first, falling back to
   `compliance_checks` — but it's a coexistence pattern that needs to
   end before another year passes. Logged in VALIDATION_LOG.md
   Block 11 (point 3).

3. **The seed dimension count grew from 16 (Block 4 design) to 23
   (after Blocks 15 & 18).** Six runtime/operation rows added that
   weren't in the original allocation table. The dimensions table
   absorbing this without code change is the configuration-first
   principle paying off in a way that's easy to skim past — there's
   genuinely no Python edit to support a new dimension.

4. **The dashboard's brief cell needs a fallback for legacy prompts.**
   Briefs link forward via `brief.resulting_prompt_id`; prompts created
   pre-Brief-Builder never had a brief. The dashboard treats the
   absence as `Complete` so legacy rows still render meaningfully. The
   alternative (`—` for "no brief") would have made every imported
   prompt look unfinished. Pragmatic but a touch white-lie; F21.3
   logs the proper fix.

5. **`audit_log.entity_type` is too narrow.** The CHECK constraint
   was sized for the original entity set and now blocks
   DeploymentRecord / OperationRecord audit rows. The deployment and
   operation routers all write 'PromptVersion' as the entity_type,
   which is misleading in audit queries. Fixing this is a CHECK
   widening — small migration, but a migration nonetheless. Parked in
   PHASE3 §F21.5.

6. **Role hierarchy got duplicated three times.** `_ROLE_RANK = {Maker:1,
   Checker:2, Admin:3}` is in `app/routers/deployments.py`,
   `app/routers/operations.py`, and `app/routers/build_gate.py`. None
   of these knew about each other when written; the duplication wasn't
   caught until Block 22. Not violating the configuration-first
   principle (role hierarchy is a domain fact, not config), but
   begging for a `services/access.py` helper. PHASE3 cross-cutting.

7. **The pace.** BUILD_PROTOCOLS §9 estimated Phases 3-6 at 13-22
   sessions; this run did them in one sitting. The estimate assumes
   Tier C / D protocol with chat-Claude review per file. Running
   autonomously (Tier B+C compressed) is faster but loses the chat-
   review backstop. Specifically, the dashboard JS rewrite went in
   without a browser test, and three of the seven F21 findings would
   plausibly have been caught earlier under Tier C.

---

## Test count by block

| State | Tests |
|---|---|
| Start of session (Block 11 done) | 193 |
| After Block 13 | 210 |
| After Block 15 | 219 |
| After Block 16 | 229 |
| After Block 18 | 242 |
| After Block 20 | 254 |
| After Block 22 | 264 |

71 new tests added across the run. None hard-code production dimension
codes. Synthetic phase fixtures (TEST_*) were used wherever the engine's
genericity needed to be proved.

---

## Files added

```
DEPLOYMENT_FORM_SPEC.md            (Block 12 — committed from interrupted work)
DEPLOYMENT_COMPLIANCE_SPEC.md      (Block 14)
OPERATION_SPEC.md                  (Block 17)
DASHBOARD_SPEC.md                  (Block 19)
PHASE3.md                          (Block 22)
RUN_A_COMPLETE.md                  (this file)

seed/form_fields.yml               (Block 12)

app/routers/deployments.py         (Blocks 13/15/16, with operation-create hook in Block 18)
app/routers/operations.py          (Block 18)
app/routers/dashboard.py           (Block 20)
app/routers/build_gate.py          (Block 22)

services/form_validation.py        (Block 13)
services/deployment_compliance.py  (Block 15)
services/operation_lifecycle.py    (Block 18)
services/dashboard_view.py         (Block 20)

tests/test_deployments.py          (Block 13)
tests/test_deployment_compliance.py (Block 15)
tests/test_deployment_gate.py      (Block 16)
tests/test_operation.py            (Block 18)
tests/test_dashboard.py            (Block 20)
tests/test_block21_smoke.py        (Block 21)
tests/test_build_gate.py           (Block 22)
```

Files modified:

```
app/main.py                        (router registrations)
app/routers/deployments.py         (compliance + gate + operation hook)
seed/dimensions.yml                (4 deployment + 2 operation rows)
seed/gates.yml                     (Deployment must-pass updated)
services/applicability.py          (flag rules)
static/views/dashboard.js          (4-phase row layout)
VALIDATION_LOG.md                  (Block 21 entry)
```

---

## Loose ends

The closest things to known broken-on-arrival:

- **Browser-untested dashboard JS rewrite.** `static/views/dashboard.js`
  was rewritten in Block 20 using the same patterns as the existing
  view but never run in a browser. The data path is well-tested via
  `/dashboard` API tests; the rendering path is not.
- **F21.5 / F21.6 in PHASE3 cause audit ambiguity.** Deployment gate
  rejections write `action='DefectLogged'` because no `'Rejected'`
  enum value exists. Anyone querying the audit log for "what
  happened to this deployment" sees a misleading word. A schema
  CHECK widening fixes it; out of scope for Block 22's "one fix".

Everything else is captured in `PHASE3.md` with the rationale for
deferral.

---

*Run A complete. Branch `run-a` ready for review.*
