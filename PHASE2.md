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

Observation from smoke-testing on 18 April: the current Brief Builder asks for free-text description first, then structured fields later. This is backward. Users describe without scaffolding, which encourages vague language ("summarise documents", "useful data for core systems"). The generator then receives a brief where the structured fields and the free-text description are misaligned, and the output quality suffers — a brief about "determine from fund prospectus whether [X]" produced a generic AI-governance-assessment prompt because template selection by prompt_type overrode semantic content.

### Proposed sequence

1. **Input** — what document or data goes in (with placeholder examples)
2. **Purpose** — what the AI does with it (cognitive work only, not output shape; with placeholder examples)
3. **Output format** — what shape comes out (structured choice plus placeholder for specifics, separate from purpose)
4. **Brief text** — free-form elaboration, now grounded by 1, 2, and 3 (with placeholder)
5. **Regulations and ISO standards** — guardrails, auto-suggested from prior steps, user can adjust

### Design principle

One concept per step. Each step narrow enough to have meaningful placeholder examples. Each step's answer informs the next. Compound questions (purpose + output in one step) produce vague answers. Separating them produces specific answers at each step.

Placeholders act as coaching-by-example at every step. This may reduce or eliminate the need for the separate three-tier validation layer (P3), because users are guided into specificity by example before typing.

### Open questions

- Does the current three-tier validation (P3) survive the redesign at all, or does it become unnecessary?
- Where does "audience" live? Inside purpose, inside output format, or as its own step?
- Should guardrail selection be auto-suggested with "adjust" option, or require explicit review?

### Scope and priority

Scope: frontend redesign of Brief Builder, placeholder content library, new data flow from structured steps into generator. Estimate: 4-6 hours frontend, 1-2 hours backend.

Priority: reconsider before continuing with P3 (three-tier coaching) and P4 (quality dial) as currently specified. This redesign may supersede both.

### Broader pattern

The "one concept per step" principle applies beyond the Brief Builder. Audit other user-facing forms for places that ask about multiple things at once — those are places where output quality is likely degrading.

### State loss on Back/Review navigation

Brief Builder state loss on Back/Review navigation: if the user edits the title or restructured text at the review step, then clicks Back to editing, then returns to review, loadRestructuredBrief() re-runs and overwrites their edit. Pre-existing behaviour extended to the title field in Slot T1. Fix by preserving user-edited state across Back/forward navigation — probably a 'has been edited' flag on each field plus conditional re-fetch. Estimate: 30-45 min. Not urgent.

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

---

## Three-category architecture for governance content

Observation from smoke-testing on 18 April: the generated prompt contains governance content that the LLM cannot meaningfully act on (decommission triggers, reviewer assignments, accountability chains, "AI-generated on [date]" statements). This content is wrapper metadata *about* the prompt, not runtime instructions *to* the LLM. Including it in the system prompt either clutters every output with boilerplate or gets ignored, both of which degrade quality.

**Current model:** every active scoring dimension generates a text block, all blocks concatenated into the system prompt as "TONE AND BEHAVIOUR RULES."

**Correct model:** each dimension produces content of one of three types:

1. **prompt_content** — runtime instructions for the LLM (e.g. OWASP_LLM09 "don't fabricate references," REG_D2 "cite page numbers," ISO42001_8_4 "declare uncertainty"). Goes into the prompt.
2. **wrapper_metadata** — information displayed around the LLM output, not given to the LLM (e.g. NIST_GOVERN_1 "System Owner," "Accountable reviewer," audit trail references, AI-generation disclosure with date and version). Rendered by the registry UI around the output, not fed to the LLM.
3. **registry_policy** — rules the registry machinery enforces against the prompt lifecycle, not runtime content (e.g. NIST_MANAGE_1 "decommission trigger 85% accuracy" is a monitoring rule, not a prompt instruction). Implemented in registry code, not in prompt text.

### Scope of change

- Add `content_type` column to `scoring_dimensions` table with enum `{prompt_content, wrapper_metadata, registry_policy}`
- Classify all 17 existing dimensions into the three types (manual review, ~30 minutes)
- Update `assemble_template` to only include `prompt_content` dimensions in the generated prompt
- Build UI components to render `wrapper_metadata` around displayed output
- Design `registry_policy` enforcement mechanism (monitoring dashboard, accuracy tracking, automated review triggers)

Estimate: 3-4 hours for the schema change + classification + generator update; another 4-6 hours for wrapper UI and registry policy enforcement machinery. Do in two phases.

**Priority:** high. This is the architecturally correct fix for the generator quality problem. The Brief Builder flow redesign (captured separately) addresses UX; this addresses data model. Both needed. This one is probably more important because it fixes output quality even if the flow stays as is.

## Example-based brief coaching and generator benchmarking

Observation from tonight: the Brief Builder coaching and the generator quality problem could both be addressed by a library of gold-standard example prompts drawn from public sources and the registry itself.

Two use cases:

1. Brief Builder coaching — when user starts a brief in a domain, surface 2-3 examples of how similar gold-standard briefs are worded. Placeholder-as-coaching plus example-as-coaching together.

2. Generator benchmarking — compare generated prompt against similar gold-standard prompts. Flag divergence as a quality signal. Replaces much of what the 17-dimension compliance rubric was trying to do.

Sources for the example library:
- Public prompt libraries (Anthropic cookbook, OpenAI examples, LangChain hub, PromptBase) — general patterns
- Regulatory publications (FINMA, FCA, BaFin, EU AI Act guidance) — regulated-finance-specific, authoritative
- The organisation's own registry as it grows — domain-specific, proven

Stacking model: seed with public + regulatory on day one, registry prompts augment over time, mature state is registry-dominated with public as fallback for novel categories.

Replaces or reframes:
- P3 three-tier coaching as originally specified (examples do the coaching, not LLM judgement)
- "Quality threshold" problem in Brief Builder redesign (similarity to gold-standard briefs = threshold)
- Parts of the 17-dimension compliance rubric (benchmark against proven-good prompts, not abstract criteria)

Scope: seeded example library (~30 examples to start, curated by hand), semantic similarity search (embeddings, stored in Postgres pgvector or similar), comparison UI for Brief Builder, benchmarking logic in generator. Estimate: 6-10 hours for first cut, more for polished.

Priority: after Brief Builder flow redesign ships. Complementary feature, not competing priority.

Open question: who owns curating the seeded example library? Charlie Hainsworth at EY is a plausible collaborator given his Tax Technology and Transformation remit. Regulatory example harvesting is half-day of research.

## Future optimisations

Cache invalidation trigger fn_invalidate_cache_on_dimension_update fires on every column update to scoring_dimensions, including columns that don't affect compliance scoring (instructional_text, updated_at, updated_by). Makes cache re-computation wasteful for display-only edits. Optimise by making the trigger conditional on specific columns (OLD.score_5_criteria != NEW.score_5_criteria OR OLD.is_active != NEW.is_active, etc.) once registry scale makes the waste noticeable. Not urgent.

## Infrastructure surfaced by dimension writing

As each scoring dimension's instructional_text gets written, it surfaces infrastructure gaps that the prompt registry currently does not have. Track these here so they're not lost.

### Runtime variable injection system
Prompts contain placeholders like {generation_date}, {version_number}, {author}, {client_name}. At invocation time (not generation time), the calling code substitutes real values for the placeholders before passing the prompt to the LLM. Required for: REG_D2 AUDIT section content, any prompt that needs session-specific or context-specific values.

Design questions: which variables are supported (fixed list vs dynamic)? Who provides values (runtime caller, registry automatic, user)? What happens when a value is missing (error, literal placeholder, empty string)? Who can define new variables?

Scope: moderate. Probably a VariableResolver service called by the prompt-run endpoint before forwarding to Claude. Estimate: 4-6 hours for first cut.

### Admin settings for registry-wide configuration
The registry needs configurable values: date format (DD-MMM-YYYY vs ISO 8601 vs locale-specific), organisation name, default author when not otherwise specified, AUDIT field list, probably more. Admin-editable at /admin/settings.

Scope: small once admin page infrastructure exists. Schema: new settings table with key-value pairs, seeded with defaults. Admin page lists and edits. Generator/runtime reads on each invocation. Estimate: 2-3 hours.

### Configurable AUDIT field list
The AUDIT section at the end of every compliant prompt should contain a configurable list of fields, not a hardcoded set. Admin chooses which fields (generation_date, version_number, author, prompt_id, compliance_grade, regulatory_scope, etc.). REG_D2's instructional_text is already written to support this — the LLM renders whatever field list is provided.

Scope: depends on runtime variable injection and admin settings. Once those exist, this is 1-2 hours. Until then, AUDIT fields are implicit in what the prompt runtime passes.

## Dimension migration pattern

For each scoring dimension that gets migrated to DB-driven instructional_text:
1. Add instructional_text to the _DIMENSIONS dict entry (benefits fresh DBs)
2. Add a targeted post-seed UPDATE to the seed file that syncs instructional_text for that specific code (benefits existing DBs)
3. Delete the corresponding entry from REGULATORY_COMPONENTS (or whatever static dict holds it) in services/prompt_components.py

Once all 17 dimensions are migrated, REGULATORY_COMPONENTS (and any sibling static dicts) can be removed entirely, closing the dual-source-of-truth problem that was flagged as Pass 2 Task 4 in an earlier PHASE2 section. Track progress on migration via this section.

Migrated so far:
- REG_D2 (Transparency) — Slot A3, 2026-04-19

## Smoke-test insight from 19 April

The generator currently has two parallel guardrail-content systems: DB-driven (scoring_dimensions rows rendered into the prompt via guardrail_block in generation.py) and code-driven (REGULATORY_COMPONENTS dict in prompt_components.py rendered via assemble_template). Both produce text about the same dimensions, creating duplication and occasional contradiction in the generated prompt. This was a root cause of the "governance-flavoured output" observation from 18 April smoke testing. The dimension migration pattern above resolves this per-dimension as each is migrated.

## Next session priorities (after 19 April)

### 1. Focus on generating good quality briefs
The Brief Builder produces acceptable briefs today but quality is inconsistent — output depends heavily on how specifically the user phrases things and which coaching question options they pick. Needs:
- Multi-select support on coaching questions (single-select is a real limitation surfaced in 19 April smoke testing — user wanted 3 of 6 options for "what cut-off time information")
- Revisit how Claude's coaching prompt consumes multi-select answers
- Consider whether the coaching threshold ("when is the brief good enough") should become configurable rather than hardcoded

Estimate: 60-90 min for multi-select alone; add 30-45 min if quality threshold work is included.

### 2. Page/section references in extracted outputs
Any prompt whose input is a document (prospectus, policy, circular, report) should produce outputs that cite the source page or section for each extracted data point. Example: "Subscription cut-off: 14:00 CET (prospectus page 23, 'Dealing Procedures' section)."

This is load-bearing for regulated-finance audit: a reviewer needs to trace every AI-extracted claim back to source. Already flagged as a design principle in an earlier PHASE2 section (page references as default component) — next session should implement it as a component that's auto-attached when input_type is a document.

Implementation: new prompt_component "OUTPUT_PAGE_CITATIONS" with plain-English instruction text, auto-selected in assemble_template when input_type matches document-like values ("PDF", "document", "prospectus", "report", "circular", "policy").

Estimate: 60-90 min including testing.

### 3. Token cost display on generated prompts
Every generated prompt should display its estimated run cost per invocation and projected annual cost at typical usage. Pre-empts the "is this getting too expensive" objection before it's asked — by showing concretely that governance-enhanced prompts cost pennies, not pounds.

Display format: "Estimated cost per invocation: $X.XX | Annual cost at 1/day: $YYY.YY | Annual cost at 1/hour: $ZZZ.ZZ"

Needs: token-counting logic (use tiktoken or similar for input estimation + max_tokens for output ceiling), current Claude Sonnet pricing as a configuration value, admin-settable usage assumption defaults.

Estimate: 90-120 min realistic including the admin setting plumbing.

### 4. Continued dimension migration (blocked on Session B)

16 scoring dimensions still render via the old code-labelled format (REG_D1, REG_D3-6, OWASP_LLM02, OWASP_LLM06-09, NIST_GOVERN_1, NIST_MAP_1, NIST_MEASURE_1, NIST_MANAGE_1, ISO42001_6_1, ISO42001_8_4). Infrastructure to migrate them is fully in place (schema, variable resolver, generator fallback, idempotent sync pattern).

Remaining work: author plain-English instructional_text for each. Approx 10-15 min per dimension = 3-4 hours total authoring time, best done in small chunks over several sessions rather than all at once.

Blocked on Session B (admin/dimensions page). Without the admin page, each migration is a code-commit-push-deploy cycle, which is heavyweight for content work. With the admin page, each migration is a UI edit — 10 min end to end.

Suggested sequence: Session B first, then bulk dimension authoring, then the three priorities above (multi-select, page citations, cost display).

### 5. Brief-type-aware validation rubrics

`validate_brief` currently uses one generic three-element rubric (Specific data / Clear output / Clear next step) for every prompt type. Extraction briefs, classification briefs, summarisation briefs, and comparison briefs each have different mandatory elements — classification needs defined categories and tie-break rules; extraction needs confidence reporting and a null-handling policy; summarisation needs length constraint and inclusion/exclusion criteria; comparison needs defined criteria and a scoring basis.

Swap in a rubric selected by `prompt_type` so validation pressure matches the real prompt-design decisions for that class. Non-trivial: needs 4-6 tailored rubrics and a selector. Estimate: 3-4 hours.
