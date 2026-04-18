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
