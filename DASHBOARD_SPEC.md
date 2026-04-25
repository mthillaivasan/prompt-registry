# DASHBOARD_SPEC.md — Block 19

The dashboard is the single view of every prompt's lifecycle state.
Each prompt is a row. The columns are the four phases the architecture
defines: **Brief, Build, Deployment, Operation**. Gates passed are
shown inline at the boundary between two columns.

---

## 1. The shape

Every active prompt sits on one row. Columns left-to-right show how far
the prompt has progressed; cells say what state that phase is in for
this prompt.

```
┌──────────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ Prompt           │  Brief       │  Build       │  Deployment  │  Operation   │
├──────────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Risk Review v3   │  ✓ Complete  │  ✓ Pass 87   │  ✓ Approved  │  Active      │
│ Loan Summary v1  │  ✓ Complete  │  PWW 64      │  Pending     │  —           │
│ KYC Classifier   │  ✓ Complete  │  Fail 41 🚫  │  —           │  —           │
│ Comms Draft v2   │  In progress │  —           │  —           │  —           │
│ Reg Map v1       │  ✓ Complete  │  ✓ Pass 92   │  ✓ Approved  │  Under Rev.  │
│ Old Pricing v0   │  ✓ Complete  │  ✓ Pass 81   │  ✓ Approved  │  Retired     │
└──────────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

Cell values are *config-driven labels* with a state colour. The
component does not branch on phase code; the renderer reads the row
data and applies the same display logic per cell.

---

## 2. Cell vocabulary

A finite, generic set of cell shapes. The dashboard renderer matches a
row's data to one of these and styles accordingly.

| State word | Source | Colour |
|---|---|---|
| `In progress` | brief.status / deployment.status = Draft | grey |
| `Complete` | brief.status = Complete; build run exists | green |
| `Pass <N>` | latest compliance run for this phase, overall_result=Pass | green |
| `PWW <N>` | overall_result=Pass with warnings | amber |
| `Fail <N>` | overall_result=Fail | red |
| `Pending` | deployment.status = Pending Approval | amber |
| `Approved` | gate fired Approved (most recent) | green |
| `Rejected` | gate fired Rejected (most recent) | red |
| `Active` | operation.state = Active | green |
| `Under Review` | operation.state = Under Review | amber |
| `Suspended` | operation.state = Suspended | red |
| `Retired` | operation.state = Retired | grey |
| `—` | the prompt has not reached this phase yet | neutral |

`<N>` is the composite_grade rendered as an integer (0–100). The label
"Pass / PWW / Fail" is read from the run row, not derived in the
renderer.

---

## 3. Gates as inline markers

A gate-fired-Approved transition between two phases is a small green
shield/checkmark rendered between columns. Hover or click reveals the
gate decision: who approved, when, rationale, the run_id evaluated.

A gate is shown only when:

1. There is a `gate_decisions` row whose `subject_type` and `subject_id`
   match the most-recent record of the upstream phase.
2. The decision was `Approved`.

Rejected gate decisions are not shown at the boundary marker; the row's
downstream column shows `Rejected` instead.

The Build → Deployment marker reads from
`gate_decisions WHERE subject_type='prompt_version'` joined to the
prompt's active version. The Deployment → Operation marker reads from
`gate_decisions WHERE subject_type='deployment_record'` joined to the
deployment record displayed in the Deployment cell.

---

## 4. The lifecycle state model

The dashboard formalises the lifecycle as a finite state machine the
data already encodes. No new state is introduced; the model below
describes what can be derived from existing tables.

```
Prompt creation
       │
       ▼
   BRIEF[In progress]
       │  brief.status = Complete
       ▼
   BUILD[—]
       │  compliance_runs (build, prompt_version) exists
       ▼
   BUILD[Pass | PWW | Fail]
       │  gate_decisions[build] Approved
       ▼
   DEPLOYMENT[—]
       │  deployment_records exists, status=Draft
       ▼
   DEPLOYMENT[Draft|Pending|Pass|Fail|Approved|Rejected]
       │  gate_decisions[deployment] Approved
       ▼
   OPERATION[—]
       │  operation_records exists
       ▼
   OPERATION[Active | Under Review | Suspended | Retired]
```

Each step is a join against a table that already exists. The
dashboard's data path is one query per row; not a phase-specific
query.

---

## 5. Endpoint contract — Block 20

A single endpoint produces the dashboard payload:

```
GET /dashboard
```

Response shape:

```
{
  "prompts": [
    {
      "prompt_id": "...",
      "title": "...",
      "prompt_type": "...",
      "risk_tier": "...",
      "owner_id": "...",
      "brief":      {"state": "Complete",   "label": "✓ Complete"},
      "build":      {"state": "Pass",       "label": "✓ Pass 87",  "grade": 87,
                     "run_id": "..."},
      "build_gate": {"decided_at": "...", "decided_by": "...",
                     "rationale": "..."},
      "deployment": {"state": "Approved",   "label": "✓ Approved",
                     "deployment_id": "..."},
      "deployment_gate": {"decided_at": "...", "decided_by": "...",
                          "rationale": "..."},
      "operation":  {"state": "Active",     "label": "Active",
                     "operation_id": "..."}
    },
    ...
  ]
}
```

The `state` value from each phase cell is one of the words listed in
§2; the renderer maps state → colour through a single lookup. No
branch on phase code in the JS or in the API.

---

## 6. Filtering and sort

Phase 2 dashboard supports:

- Filter by **owner** (default = current user; toggle "All owners").
- Filter by **risk tier**.
- Filter by **lifecycle state** (any of: at-Brief, at-Build, at-Deployment,
  at-Operation, retired-only).
- Sort by **prompt title** or **most-recent activity timestamp**
  (default).

Filters and sort are query parameters on `/dashboard`. The endpoint
returns the whole filtered set (no pagination in v1; paginate when row
count exceeds 200 rows in production).

---

## 7. What this spec does not introduce

- **No per-phase endpoint splits.** Once `/dashboard` is the canonical
  read path, the existing per-phase endpoints (`/prompts`,
  `/deployments`, `/operation`) remain for direct access — they are
  not replaced.
- **No new state words.** The vocabulary above is the closed set. A new
  state in any phase is a phase change, not a dashboard change.
- **No bespoke columns.** Custom columns (deadlines, owners, tags)
  remain a Phase 3 candidate.
- **No drill-in views.** Clicking a cell navigates to the phase's
  existing detail page — the dashboard is read-only.
- **No real-time updates.** Plain HTTP poll on a 30s cadence in v1.
  WebSocket / SSE is a Phase 3 candidate if the dashboard becomes the
  primary monitoring surface.

---

## 8. Block 20 build outline

1. `app/routers/dashboard.py` — single GET endpoint that joins per-row
   state from prompts → briefs → compliance_runs → deployment_records
   → operation_records → gate_decisions.
2. `services/dashboard_view.py` — pure functions that map a row's
   joined data to `(state, label)` per cell. Generic — driven by the
   §2 vocabulary table, not by phase code branches.
3. `static/views/dashboard.js` — the existing dashboard view rewritten
   to render the new endpoint. Existing row-based layout retained;
   columns swapped to the four-phase model.
4. Tests — synthetic prompts at each lifecycle position; verify the
   correct cell vocabulary lands on each row.

---

*Block 19 complete. Block 20 wires this spec.*
