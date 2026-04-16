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
