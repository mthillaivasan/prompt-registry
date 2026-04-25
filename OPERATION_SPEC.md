# OPERATION_SPEC.md — Block 17

The Operation phase is **what happens after Deployment approval**. A
deployed prompt has an `operation_record` from the moment its gate
fires; the record holds review cadence, incident log, and retirement
state. The Operation compliance engine runs on cadence (configurable),
on incident, or on demand.

This document is the spec. Block 18 builds it.

---

## 1. Reuse confirmation

Same as Block 14 → Block 15: **the engine itself is unchanged**.
`run_phase_compliance(phase_code='operation', ...)` is the entry point.
The `operation_records` table already exists from Block 7's migration
(`SCHEMA_V2.md` §record tables). What Block 18 adds:

1. Auto-creation of an `operation_record` when a Deployment gate fires
   `Approved` (Block 16's hook point).
2. Operation-tagged dimensions in `seed/dimensions.yml`.
3. A serialiser turning an `operation_record` into the
   `(scoring_input_text, metadata)` pair the engine expects.
4. Endpoints for cadence-driven and incident-triggered runs.
5. A retirement primitive — `state = 'Retired'`, `retired_at`,
   `retired_reason` — accessible via API.

No engine code is rewritten. No phase branches are introduced.

---

## 2. Operation lifecycle

```
gate fires Approved on a deployment_record
        │
        ▼
operation_record created
  state = 'Active'
  next_review_date = now + cadence_days  (cadence read from config)
  incidents_json = []
        │
        ├─── cadence elapses → Operation compliance run ──► result feeds review
        │
        ├─── incident reported  → append to incidents_json
        │                          → if severity ≥ threshold, trigger
        │                            Operation run + flip state to 'Under Review'
        │
        ├─── retirement trigger fires (config-driven rule) → state='Retired'
        │
        └─── manual retire by Admin/Checker            → state='Retired'
```

### State transitions

| From | To | Trigger |
|---|---|---|
| Active | Under Review | Incident with severity ≥ config threshold |
| Active | Under Review | Cadence-driven run produces overall_result='Fail' |
| Under Review | Active | Cadence run after a remediation produces 'Pass' |
| Active / Under Review | Retired | Manual decision OR retirement-trigger rule fires |

`Suspended` is reserved for emergency holds; out of scope for Block 18,
parked for Phase 3.

---

## 3. Configuration — what is data, what is code

### Cadence

Cadence (in days) is **not** a constant. Three sources, in order of
precedence:

1. The `operation_record.review_cadence_days` snapshot, set at record
   creation from the deployment's
   `change_review_frequency_days` form response — already captured in
   the Block 12 deployment form.
2. If absent, the operation phase's default cadence (new
   `phases.default_review_cadence_days` column added in Block 18 if the
   Phase row does not already accept it — Block 17 verifies first).
3. If absent, the global default 90 days.

The Operation phase row in `seed/phases.yml` carries the default. No
hard-coded interval lives in code.

### Retirement triggers

Retirement is a rule, not a button. The rules live in a new seed file
`seed/retirement_triggers.yml` (loaded by `seed_phase2.run_phase2_seed`)
into a `retirement_triggers` table:

```
retirement_triggers:
  - code: stale_review
    description: Operation record overdue by more than the trigger window
    rule: {"if_overdue_days_at_least": 60}
    action: flag_for_retirement       # writes incident; does not auto-retire
    severity: High

  - code: repeat_fail
    description: Two consecutive Operation runs return 'Fail'
    rule: {"if_consecutive_fails_at_least": 2}
    action: flag_for_retirement
    severity: Critical
```

The rule grammar mirrors the applicability grammar — closed list,
extended in code, evaluated generically. The engine never branches on
rule code.

`flag_for_retirement` writes an incident with `retire_recommended=true`
and flips `state='Under Review'`. Actual retirement remains a decision
recorded by an Admin/Checker via the `state='Retired'` endpoint;
auto-retire is parked for Phase 3 (irreversible state changes need a
Checker in the loop, per the firm's audit posture).

### Dimensions

Two Operation-tagged dimensions land in `seed/dimensions.yml` at
Block 18:

| Code | Standard | What it scores |
|---|---|---|
| NIST_MEASURE_RUNTIME | NIST_AI_RMF MEASURE 2.3 | Whether collected metrics align with the Build declaration of `NIST_MEASURE_QUALITY` |
| NIST_MANAGE_DECOMMISSION_RUNTIME | NIST_AI_RMF MANAGE 2.4 | Whether incident frequency or stale review is breaching the declared decommission trigger |

Both have applicability `{"always": true}` for Phase 2; refinements
deferred to Phase 3 once real Operation telemetry exists.

---

## 4. Incident schema

`operation_records.incidents_json` is an append-only JSON array. Each
incident:

```
{
  "incident_id": "<uuid>",
  "timestamp": "<iso>",
  "reporter": "<user_id or 'SYSTEM'>",
  "severity": "Low | Medium | High | Critical",
  "category": "Quality | Misuse | Security | Other",
  "summary": "<text>",
  "linked_run_id": "<run_id or null>",
  "retire_recommended": false
}
```

Severity threshold for auto-flipping to `Under Review` is config:
`phases.operation` row carries `incident_review_severity` (default
`High`). Read at runtime; no constant in code.

---

## 5. Cadence-run trigger

The cadence-run is fired by:

- A nightly scheduled task (out of scope for Block 18 — see PHASE3.md;
  the Block 18 build provides a `POST /operation/{id}/run` endpoint a
  scheduler can call).
- A manual run-on-demand endpoint (`POST /operation/{id}/run`).
- An incident with severity ≥ threshold.

In all three cases the engine call is identical:
`run_phase_compliance(phase_code='operation', subject_type='operation_record',
subject_id=record.operation_id, ...)`.

After a successful run, `next_review_date` is bumped:
`now + review_cadence_days`. After a failed run, `next_review_date`
becomes `now + (review_cadence_days // 4)` so that the next
re-evaluation arrives sooner — but this number lives in
`phases.operation.failed_run_review_factor` (config), not in code.

---

## 6. Endpoints (Block 18 contract)

```
POST /operation                            # auto-called from Block 16 gate
GET  /operation/{id}                       # full record
GET  /operation                            # list, filterable by state
POST /operation/{id}/run                   # cadence-driven or on-demand
POST /operation/{id}/incidents             # append incident
POST /operation/{id}/retire                # mark Retired (Checker/Admin)
POST /operation/{id}/return-to-active      # Under Review → Active
GET  /operation/{id}/runs                  # compliance runs against this record
```

The API surface is small. The lifecycle state model is in the data
model; the endpoints are the verbs against it.

---

## 7. What this spec rejects

- **Hard-coded cadence intervals.** Every interval is a config value
  (`review_cadence_days`, `incident_review_severity`,
  `failed_run_review_factor`).
- **Per-dimension Operation logic.** The two new dimensions are
  rubric-only; they are scored by the same engine that scores Build and
  Deployment.
- **Auto-retire.** Retire stays a Checker decision. Triggers
  *recommend*; humans *decide*. Auto-retire is a Phase 3 candidate
  pending evidence that the trigger rules are calibrated.
- **A new compliance engine.** Same engine, different phase, different
  scoring input shape (an `operation_record`, not prompt text).
- **Inline scheduler.** The nightly run is an external concern;
  Block 18 exposes the endpoint a scheduler can call.

---

## 8. Risk and rollout note

Operation is the first phase the registry runs *continuously*, not on
demand. Two consequences:

1. **Volume.** A live deployment may produce one cadence-run every 90
   days, but incident counts are unbounded. The `incidents_json` blob
   on the record bounds growth at row-rewrite time; if a record
   accumulates more than ~100 incidents, splitting incidents into a
   table is the logical next refactor (parked, PHASE3.md).
2. **Telemetry.** The Operation engine scores against the
   `operation_record` state, not against live runtime telemetry. Wiring
   real telemetry — error rates, drift signals, output samples —
   requires an upstream pipeline that is out of scope for this refactor
   round. Block 18 captures what is captureable today; the rest is
   PHASE3 work.

These constraints keep Block 18 honest about what is being built versus
what is being readied for.

---

*Block 17 complete. Block 18 wires this spec.*
