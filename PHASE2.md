# Phase 2 Backlog

Items logged here are explicitly outside the two MVP journeys. They must not be built in Phase 1.

---

## P2-001 — PDF Audit Report
Generate a formatted PDF export of the full audit trail for a prompt, including all versions, compliance check results, defect history, and approvals. Useful for regulatory submissions. Not built in MVP.

## P2-002 — Admin UI for Dimension Management
A UI for creating, editing, and deactivating ScoringDimension records. In MVP, dimensions are seeded at migration and managed directly in the database by an administrator.

## P2-003 — Multi-Tenant Architecture
Isolate data and configuration per organisation. MVP is single-tenant only.

## P2-004 — Regulation Change Feed and Notification Engine
Monitor regulatory sources (EU AI Act, FINMA, FCA) for updates and notify owners when a change affects their active prompts. Not built in MVP.

## P2-005 — PDF Generation (WeasyHTML or equivalent)
Any server-side HTML-to-PDF rendering. Blocked in MVP.

## P2-006 — Bulk Import from SharePoint or External Sources
Import existing prompt libraries from SharePoint, Confluence, or file uploads. MVP supports single-prompt paste only.

## P2-007 — Brief Builder
A guided five-question flow that converts a one-line user description into a structured prompt brief. Front-door feature for non-technical users. Feeds directly into the generator. Strong SaaS adoption candidate.

## P2-008 — Advanced Inventory Dashboard Filtering
Filter the prompt inventory by owner, framework score, date range, deployment target, or dimension gaps. MVP shows a simple list filtered by status only.

## P2-009 — Charts, Visualisations, and Analytics
Trend charts, score distributions, defect rates, and compliance dashboards. Not built in MVP.

## P2-010 — Model Alias Note
The build spec references model `claude-sonnet-4-20250514`. If this identifier is not accepted by the Anthropic API at runtime, fall back to `claude-sonnet-4-6` and investigate whether the two identifiers resolve to the same model. Confirm the correct production alias before Phase 2 release.

---

## Deferred from Pass 1

- **Schema authority model is split between SQL and Python for runtime asserts.** 001_initial.sql is authoritative for Postgres structure; triggers.py runs CREATE OR REPLACE FUNCTION on every startup as idempotent re-assertion. Indexes are only in the authoritative SQL (no duplication). This pattern works but creates two places where Postgres schema logic can drift if someone only updates one. Revisit if SQLite is dropped as a target: everything can move to declarative SQL per backend.

- **Timestamp columns stored as TEXT instead of TIMESTAMPTZ.** All timestamp columns in the SQLAlchemy models use `Column(String)` and store ISO 8601 strings (e.g. `"2026-04-18T10:30:00Z"`). The authoritative SQL (`001_initial.sql`) was updated to match this, using `TEXT` columns rather than `TIMESTAMPTZ`. This should be fixed by changing SQLAlchemy models to `Column(DateTime(timezone=True))` and updating all timestamp writers. Scope: `models.py`, all routers/services that write timestamps, all `_utcnow()` helpers. Estimate: 2-3 hours.

---

## Design issues surfaced in Pass 2

- **`check_tier2_trigger` in `services/guardrails.py` contains hardcoded dimension codes** (REG_D2, REG_D3, REG_D5, REG_D6, OWASP_LLM01, OWASP_LLM06) with bespoke trigger logic for each. Adding a new tier-2 dimension to the database cannot fire a trigger without editing this function. The trigger condition should move to a column on the scoring_dimensions table (e.g. a JSON `tier2_conditions` field). Scope: schema change, data migration for existing dimensions, function rewrite. Estimate: 2-3 hours.

---

## Pass 2 notes

- `check_tier2_trigger` and `resolve_guardrails` were promoted from module-private helpers (underscore prefix) in `prompts.py` and `compliance.py` to public functions in `services/guardrails.py` (no underscore), following Python convention for exportable service-module functions. Importers now use the underscore-free names. This was a deliberate convention change, not a gratuitous rename — the underscore prefix would have been a PEP 8 anti-pattern once the functions became cross-module imports.

---

## Brief Builder flow redesign

Observation from smoke-testing on 18 April: the Brief Builder asks for free-text description first, then structured fields (input type, output type, audience, deployment target) later. This is backward.

**Implications:**

1. Validation questions on the initial description are premature — they ask the user to solve specificity that the next steps are designed to address.
2. Users describe without scaffolding, which encourages vague language.
3. The generator receives a brief where structured fields and free-text description are misaligned, because they were gathered out of sequence.
4. The generator's output quality suffers — a brief about "determine from fund prospectus whether [X]" produced a generic AI-governance-assessment prompt because the template selection overrode the semantic content.

**Proposed redesign:**

1. Structured fields first (dropdowns, fast)
2. Purpose free-text (now framed by choices already made)
3. Validation AFTER purpose (now meaningful)
4. Guardrail selection (auto-suggested from structured + purpose)
5. Review and restructure
6. Generate

This changes P3 (three-tier coaching) materially — polishing coaching on a wrongly-ordered flow is the wrong priority. Reconsider P3 after flow redesign.

Estimate: flow redesign is 4-6 hours frontend + 1-2 hours backend. Significantly higher than P3 as originally scoped.

---

## Learning layer from completed prompts

Once the registry contains N (TBD, suggest 10+) active prompts with compliance scores, the Brief Builder should use them as guidance when building new briefs in similar domains.

**Mechanism:** when a user starts a new brief, match against existing Active prompts by `prompt_type`, `input_type`, `output_type`, and semantic similarity of purpose. Surface the top 2-3 matches during Brief Builder as "users building similar prompts made these choices." Optionally pre-fill structured fields from the closest match.

**Effect:** coaching gets smarter as the registry grows. Eliminates much of the need for generic Tier 3 questioning for mature prompt domains.

**Scope:** semantic similarity scoring (embeddings), UI for displaying similar-prompt guidance, data flow from registry into Brief Builder. Estimate: 4-6 hours first cut.

**Dependency:** reconsider alongside Brief Builder flow redesign in the same section. May replace P3 coaching entirely.

---

## Page references as default component

Any prompt whose `input_type` is a document (prospectus, policy, circular, report) should by default include an output instruction requiring page references or section citations for extracted content. Example: "Cite the source page or section for each data point extracted."

This is load-bearing for regulated-finance use: an auditor needs to verify outputs against source material, and that only works if the AI reports where in the document each finding came from.

**Implementation:** add a new component to `prompt_components` table — code `OUTPUT_PAGE_CITATIONS`, category `OutputFormat`. Mark it as auto-selected when `input_type` matches document-like values. Update the generator's `assemble_template` to include it by default for document inputs.

**Scope:** one new component seed, one rule in `assemble_template`, possibly a schema addition for auto-select metadata on components. Estimate: 1-2 hours.

**Priority:** high. This should probably happen before the EY Summit rather than after, because "AI output with citations" is exactly the credibility feature an EY partner would look for.
