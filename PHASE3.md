# PHASE3.md

Parking lot for items deferred from the Phase 2 refactor. The scope
discipline of the 22-block plan parks items here when they surface
mid-block; this file is the reconciliation point for the next refactor
round.

Items are listed under their Phase 2 source. Each carries:

- **Source** — the block or smoke pass where it surfaced.
- **What** — a one-line description of the change.
- **Why parked** — what scope rule moved it here (out of block scope, a
  schema change too large for the block, or a feature genuinely
  belonging to a later phase).

---

## From REFACTOR_PLAN.md §7 (Phase 3 candidates known at planning time)

- Brief Builder question text as configuration.
- Admin UI for managing dimensions, standards, gates (currently
  seed-only).
- Automated compliance iteration (P7, reconsider).
- Mobile-ready architecture (P11).
- Token cost display (P8) — slot opportunistically pre-Block 22 (status:
  not yet slotted; remains parked).
- Cross-phase dependency rules (e.g. Deployment dim X blocks if Build
  dim Y scored below threshold).
- Historical version comparison across refactors.
- Multi-tenant / client-scoped configuration overlays.

---

## From Block 11 — Build smoke

- Drop `framework_averages` from compliance check responses (legacy
  shape) once UI consumers move to `by_standard`. Coordinated
  Block 22+ cleanup.
- `OWASP_SYSTEM_PROMPT_LEAKAGE` instructional text revision: it
  conflates role-declaration (OK) with role-echo-on-demand (the
  actual risk). Needs a rewrite once real LLM smoke evidence exists.

## From Block 14 — Deployment compliance spec

- (Resolved in Block 15) — initial spec deferred the Deployment-side
  ISO42001_DATA_GOVERNANCE counterpart. Block 15 added it.

## From Block 17 — Operation spec

- `seed/retirement_triggers.yml` and the corresponding
  `retirement_triggers` table. Spec'd in OPERATION_SPEC §3 but not
  implemented in Block 18. The rule schema exists on paper; the table
  and seed loader hooks remain. Without them, retirement is purely a
  manual decision.
- `phases.operation` columns for cadence default, severity threshold,
  failed-run review factor. The Phase row carries no such columns
  today; values fall through to constants in
  `services/operation_lifecycle.py`. The constants are documented but
  the principle wants config rows.
- Auto-retire (a trigger fires and retires a record without a Checker).
  Parked because retire is irreversible state and the firm's audit
  posture wants a human in the loop. Reconsider after trigger rules
  have lived for a quarter and their false-positive rate is known.
- Nightly scheduler that calls `POST /operation/{id}/run`. Block 18
  exposes the endpoint but does not deploy a scheduler — out of
  refactor scope.
- Splitting `incidents_json` into a row-per-incident table once any
  record exceeds ~100 incidents.

## From Block 21 — End-to-end smoke

- **F21.1** — Resolved in Block 22 (Build → Deployment gate endpoint).
- **F21.2** — Brief PATCH should return a clearer error when callers
  attempt to set `status` on a payload PATCH cannot honour.
  Discoverability fix; does not change behaviour.
- **F21.3** — Wire `POST /prompts` to backfill the source brief's
  `resulting_prompt_id` when the brief id is supplied. Without this,
  the dashboard's Brief cell falls back to "Complete" via legacy
  fallback rather than naming the actual brief.
- **F21.4** — Clean up `prompts.deployment_target` legacy column once
  all readers move to `ai_platform` / `output_destination`. Out of
  Phase 2 scope per REFACTOR_PLAN §3 transitions.
- **F21.5** — Widen the `audit_log` `entity_type` CHECK constraint to
  add `'DeploymentRecord'` and `'OperationRecord'`. Today the
  deployment and operation routers use `'PromptVersion'` as the
  closest match, which is misleading in audit queries.
- **F21.6** — Widen the `audit_log` `action` CHECK constraint to add
  `'Rejected'` and `'GateDecided'`. Rejected gate firings currently
  log as `'DefectLogged'` because the action enum has no rejection
  word. Misleading in the audit timeline.
- **F21.7** — Move the operation cadence/severity/failed-factor
  constants into a `phases` row column. See Block 17 entry above.

---

## Cross-cutting

- **Single source of truth for role hierarchy.** The role-rank dict
  (`Maker:1, Checker:2, Admin:3`) is duplicated across
  `app/routers/deployments.py`, `app/routers/operations.py`, and
  `app/routers/build_gate.py`. A small helper module would consolidate
  it. Trivial; bundle with the next router-level refactor.
- **Typed `PhaseCode`** — a `Literal['build','deployment','operation']`
  alias in `schemas.py` would help static analysis without violating
  configuration-first (it constrains string values, not behaviour).
  Block 11 surfaced this; Block 22 doesn't slot it.

---

## Brief Builder design principle (logged 27 April 2026)

The Brief Builder's purpose is to get a user to a runnable version 1 prompt as quickly as possible, not to extract a complete specification before any code runs. Subsequent depth comes through iteration once the user has seen a model's output and knows where it falls short.

### Implications for L2 (library integration into Brief Builder)

The library should support v1-fast and iteration-deep workflows differently. On v1, library examples are passive context — shown for reference, not used to drive deeper questions. On iteration (when the user returns to refine an existing prompt), library examples become coaching: "the FINMA summary prompt specifies these output fields explicitly; yours doesn't. Add output specification?"

Conditional questioning by output structure (JSON / structured / unstructured) is deferred to iteration, not v1. v1 asks the minimum: input type, output type, domain. Anything more is an iteration concern.

### Anti-pattern to avoid

Comprehensive Brief Builder questionnaires that delay first run. The library's job is to teach by example after a v1 has been tried, not to interrogate before one exists.

---

*This file is updated by every block that defers a found item. Block
numbers in the §"From Block N" headers match the source block.*
