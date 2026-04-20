# Refactor Plan — Prompt Registry Phase 2

**Version 1.0 — 20 April 2026**
Drafted jointly with Claude. Supersedes `PHASE2.md` for all forward work.
Companion documents: `ARCHITECTURE.md` (produced in Phase 0), `PHASE3.md` (parking lot).

---

## 1. Purpose

This is the working plan for the architectural refactor of the prompt registry. It merges three things previously held separately: the three-phase lifecycle architecture (Build → Deployment → Operation), the status of everything currently in the pipeline, and the 22-block execution plan.

Work is structured in one-hour blocks with no deadline. Each block has a clear done state so a session can close cleanly. Blocks may expand to two or shrink to half; phase boundaries matter more than block boundaries.

The demo has been de-prioritised. The refactor is the work.

---

## 2. Architectural principles

The plan rests on five principles. Each downstream block is a direct expression of one or more of these. If a block cannot be traced to a principle, it does not belong in the plan.

### 2.1 Phase separation

A prompt moves through three phases, each with its own purpose, standards subset, compliance grade, and approval gate.

**Build** — brief becomes prompt. Artefact-level only. Asks: is this prompt well-constructed and secure in isolation.

**Deployment** — prompt becomes deployed capability. Runtime context captured. Asks: is this deployment safe in its actual runtime.

**Operation** — deployed capability runs. Continuous surveillance. Asks: is this still behaving, and is it still needed.

Phases are not combined into a single compliance pass. A Build grade says nothing about Deployment safety; a Deployment grade says nothing about Operation health. Each gate is separate.

### 2.2 Standards alignment

Every compliance dimension carries an explicit reference to OWASP LLM Top 10, ISO/IEC 42001, or NIST AI RMF. Anonymous dimensions (`D1`, `D2`, ...) are retired. Grades are published with their standard reference — `OWASP LLM01 — Pass`, not `D1 — Pass`. Dimensions that cannot be tagged to a standard are either retired or relabelled to match a standard the firm will defend.

### 2.3 Configuration-first — no hard-coding

**This is the principle that most of the current code violates.** Everything that can change without a code deployment must live in data, not in code.

| Hard-coded today | Moves to configuration |
|---|---|
| The 17 dimensions as Python classes/functions | A `dimensions` table with name, phase, standard reference, applicability rules, scoring prompt |
| Standards references scattered in comments | A `standards` table (OWASP, ISO 42001, NIST AI RMF) with versioned clause lookups |
| Phase-to-dimension mapping | A column on the `dimensions` table |
| Dimension applicability rules | Structured rules evaluated by a generic engine, not `if` statements in dimension code |
| Scoring rubrics and check prompts | Prompt templates stored as records, retrievable and versionable |
| Gate approval logic | Configurable per-phase gate records |
| Risk tier calculation | A rules table, not hard-coded thresholds |
| Deployment form field list | A `form_fields` table with type, validation, display rules |
| Operation review cadence, retirement triggers | Records in the operation config, not hard-coded intervals |

The code becomes a generic engine. The registry becomes configuration. When OWASP updates its Top 10, when a regulator issues new guidance, or when a new dimension is needed, the work is a config change — editable, reviewed, audited — not a code deployment.

This is not an abstract ideal. A tool that requires a code push to update a dimension is a tool that cannot keep pace with its own regulatory environment. The refactor is the opportunity to get this right once.

**Pragmatic limit.** Brief Builder question text, UI layouts, and the compliance engine's orchestration code stay in code for now. Moving Brief Builder questions to config is a proper feature for Phase 3. The rule is: anything the engine resolves, reads from config; anything that orchestrates the engine stays in code. Scope discipline matters.

### 2.4 Artefact vs audit separation

Prompt text carries only runtime behaviour. Everything else — standards references, compliance grades, approval records, version history, deployment context — lives in the audit record. This is the discipline set out in Section 6 of the training document. The tool embodies the principle it governs.

### 2.5 Lean refactor — no new features until Block 22

No new features are added to the backlog between now and the end of Block 22. Ideas surfacing during the refactor go to `PHASE3.md`. Features currently in the pipeline are either folded into the refactor, subsumed by it, or parked. See Section 3.

---

## 3. Pipeline inheritance

Everything previously in `PHASE2.md` has been reviewed against the new architecture. Status summarised below.

### 3.1 Carries forward unchanged

The tool does not stop. Users continue on the existing flow while the refactor lands in parallel.

- Variable resolver
- Title feature (end-to-end)
- Audit log (extended in Block 7 to cover new phase and gate records)
- Brief Builder shell
- F2 fix across `restructure_brief` and validate endpoints
- Current 105 tests — a portion rewritten at Block 9 (expect 15 to 30 affected)

### 3.2 Folds into the refactor

| Pipeline item | Folds into |
|---|---|
| Dimension migration (16 of 17 on old fallback) | Blocks 4, 7, 10 — only surviving dimensions migrate, into their allocated phase, with standard references, as seed data |
| Multi-select on Brief Builder | Block 9 — lands inside the Build refactor as a generic form capability, not before it |
| Page / section references in extracted outputs | Block 9 or early Phase 3 — artefact-shaping, belongs at Build |

### 3.3 Subsumed by the architecture

Retired from the backlog. Their concerns are addressed structurally by the phase separation.

| Pipeline item | Why retired |
|---|---|
| P9 tiered compliance (levels 1 / 2 / 3) | Phase-appropriate dimension subsets replace tiering |
| P7 automated compliance iteration | Wrong compliance engine to build against. Reconsider after Block 15 |
| P10 prompt summary card | Reshaped by Blocks 19-20 dashboard redesign |
| P12 design language pass | Reshaped by Blocks 19-20 |

### 3.4 Independent — slot in opportunistically

| Pipeline item | Notes |
|---|---|
| P8 token cost display | No architectural dependency. Any spare block. |
| P11 mobile-ready architecture | Strategic. Dedicated later phase, post-validation. |

---

## 4. The 22-block plan

### Phase 0 — Decide before building

Research and specification. No code.

**Block 1 — Dimension inventory.** List all 17 current dimensions in `ARCHITECTURE.md`: name, what each actually checks, what input it needs, current migration state.
*Done when:* the table is in `ARCHITECTURE.md`.

**Block 2 — OWASP LLM Top 10 tagging.** Read the current OWASP LLM Top 10. Tag each of the 10 items Build, Deployment, Operation, or vendor-side.
*Done when:* the tagged list is appended to `ARCHITECTURE.md`.

**Block 3 — ISO 42001 and NIST AI RMF tagging.** Same exercise for ISO 42001 Annex A and NIST AI RMF subcategories. Orientation pass, not a full read.
*Done when:* both are tagged in `ARCHITECTURE.md`.

**Block 4 — Dimension allocation.** Each of the 17 dimensions assigned to Build, Deployment, Operation, or Retire. Each survivor labelled with its standard reference. Output is a structured seed file — `seed/dimensions.yml` — ready to load into the database. This is the first concrete expression of the configuration-first principle: dimensions are now data.
*Done when:* every dimension has a phase and a standard label, and the seed file validates.

**Block 5 — Architecture note.** One page in `ARCHITECTURE.md`. Three phases, three gates, three standards layers, configuration-first schema sketch, how a prompt moves left to right. The spec every downstream block reads from.
*Done when:* `ARCHITECTURE.md` is complete and committed.

### Phase 1 — Schema (generic, config-driven)

**Block 6 — Schema design on paper.** `SCHEMA_V2.md` with table definitions for `dimensions`, `standards`, `phases`, `gates`, `deployment_records`, `operation_records`, `applicability_rules`, `scoring_rubrics`, `form_fields`. Each table generic — no hard-coded rows, no dimension-specific columns.
*Done when:* a reader can trace how a compliance run resolves from the schema without reference to specific dimensions or standards.

**Block 7 — Schema migration and seed.** Claude Code generates migration from `SCHEMA_V2.md`. Seed data loaded from `seed/dimensions.yml` and `seed/standards.yml`. The 17 dimensions leave Python and enter the database.
*Done when:* migration is in main, seed is loaded, tests green.

### Phase 2 — Refactor Build to artefact-only

**Block 8 — Strip-down brief.** `REFACTOR_BUILD.md` specifies which dimensions remain in Build (as config, not code), what the generic Build compliance engine reads from the `dimensions` table, and what leaves Build. No dimension-specific logic survives in Python; the engine reads config and executes.
*Done when:* the brief is in `REFACTOR_BUILD.md`.

**Block 9 — Claude Code executes the strip-down.** The Build compliance engine becomes generic: fetch Build-phase dimensions from config, run each per its rules, aggregate. Multi-select and extraction-reference enhancements land here as generic form capabilities, not dimension-specific code. Affected tests rewritten in the same block.
*Done when:* running Build on a prompt produces a grade whose dimension list comes entirely from config, tests green.

**Block 10 — Grades name their standards.** UI and API update. `D1` becomes `OWASP LLM01 — Prompt injection resistance`. The label comes from the joined `dimensions` and `standards` tables, not hard-coded.
*Done when:* activating a prompt produces a result card naming the standards, sourced from data.

**Block 11 — Smoke test Build.** Run one existing prompt through the new Build flow. Log what works, what surprises, what dimension config needs tuning.
*Done when:* observations are in `VALIDATION_LOG.md`.

### Phase 3 — Deployment workflow

**Block 12 — Deployment form spec.** `DEPLOYMENT_FORM_SPEC.md`. Fields: invocation context, input sources, output handling, monitoring cadence, runtime owner, incident response, change management. Field definitions are data — a `form_fields` table — to allow future adjustment without code change.
*Done when:* spec is committed and the field list is expressed as seed data, not inline form code.

**Block 13 — Deployment form build.** Form is live and writes to the `deployment_records` table. Fields rendered from config.
*Done when:* a deployment record can be captured end to end.

**Block 14 — Deployment compliance engine spec.** The generic engine from Block 9 is reused. It does not know whether it is running Build or Deployment, only which phase it is passed. Applicability rules determine which dimensions apply to which deployment records.
*Done when:* spec is written and confirms no new dimension-specific code.

**Block 15 — Deployment compliance build.** Engine wired in. Running it on a `deployment_record` produces a graded result with standards-labelled dimension scores.
*Done when:* a deployment produces a graded Deployment record using the same engine as Build.

**Block 16 — Deployment gate.** Approval flow. Authoriser identity captured, decision recorded, rationale logged. Gate rules (who can approve, what conditions must hold) live in the `gates` config, not in code.
*Done when:* a Deployment record can be approved or rejected with reason captured, gate rules readable from config.

### Phase 4 — Operation layer

**Block 17 — Operation spec.** `OPERATION_SPEC.md`. Review cadence, incident logging, retirement triggers. All cadences and thresholds are config, not hard-coded intervals.
*Done when:* spec is committed.

**Block 18 — Operation build.** First cut: an `operation_record` is created when a deployed prompt enters service. Record holds review date (set from config), incident entries, retirement flag.
*Done when:* every deployed prompt has a live Operation entry.

### Phase 5 — Dashboard

**Block 19 — Dashboard redesign spec.** `DASHBOARD_SPEC.md`. Columns for Brief, Build, Deployment, Operation. Each prompt is a row moving across. Gates passed shown inline. Lifecycle state model documented.
*Done when:* spec is written and sketched.

**Block 20 — Dashboard build.** Dashboard shows every prompt in its lifecycle state with gates visible. Reads from records and phase config, not hard-coded layout.
*Done when:* the dashboard renders every prompt with its current phase and gate status.

### Phase 6 — Validate against real work

**Block 21 — One real prompt end-to-end.** A prompt for actual Operations work, taken Brief → Build → gate → Deployment → gate → Operation. Every friction point logged.
*Done when:* the prompt is live in Operation, `VALIDATION_LOG.md` is written.

**Block 22 — Highest-priority fix.** One fix only, chosen from the validation log. All other items parked in `PHASE3.md`.
*Done when:* the fix is committed.

---

## 5. Test strategy during refactor

Tests currently covering the flat-dimension compliance flow will break at Block 9. Do not pre-emptively rewrite them. Let Block 9 break what it breaks, then fix in place.

Tests covering the variable resolver, title feature, audit log, Brief Builder validation, and F2 are architecturally independent and stay green throughout.

New tests introduced during the refactor must test the engine against seed configurations, not hard-coded expected dimensions. A passing test should still pass if the seed data changes to a valid alternative configuration — this is the test-side expression of the configuration-first principle.

---

## 6. Rules of engagement with Claude Code

- No auto-commits. `COMMIT READY` block, wait for `APPROVED`.
- **Any new hard-coded dimension, standard, or phase-specific logic in Python is a rejected commit.** Code handles generic cases; behaviour lives in seed data and config.
- Schema changes or API contract changes — stop and ask.
- Anything outside the current block goes in `PHASE3.md`.
- One file at a time for non-trivial work.
- Tests stay green across blocks; Block 9 is the explicit exception with affected tests rewritten in the same block.
- Before any block begins, confirm environment: `pwd` (expect `/workspaces/prompt-registry`), `git log --oneline -3`, `git status` clean.

---

## 7. Parking lot — Phase 3 candidates

Not in scope before Block 22. Noted here to prevent re-litigation.

- Brief Builder question text as configuration
- Admin UI for managing dimensions, standards, gates (currently seed-only — any change requires a seed update and reload)
- Automated compliance iteration (P7, reconsider)
- Mobile-ready architecture (P11)
- Token cost display (P8, can slot opportunistically before Block 22 if a natural break appears)
- Cross-phase dependency rules (e.g. Deployment dimension X blocks if Build dimension Y scored below threshold)
- Historical version comparison across refactors
- Multi-tenant / client-scoped configuration overlays

---

## 8. Session restart template

Paste at the start of each new chat to re-ground Claude Code:

```
Resuming prompt-registry refactor. Working against REFACTOR_PLAN.md.

Currently on Block [N] — [block title].
Done state for this block: [paste from plan].

Environment check first:
- pwd (expect /workspaces/prompt-registry)
- git log --oneline -3
- git status (clean)

Then confirm the block is understood before any work begins.
Configuration-first principle: no new hard-coded dimension, standard,
or phase-specific logic in Python. If in doubt, stop and ask.
```

---

*End of plan.*
