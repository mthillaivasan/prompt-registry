# ARCHITECTURE.md

**Prompt Registry — Refactor Architecture**
Working against `REFACTOR_PLAN.md`. This document is built up block by block across Phase 0.

---

## Block 1 — Dimension inventory

**Status:** Complete. Produced 20 April 2026 by reading `app/seed.py`, `services/compliance_engine.py`, `services/prompt_components.py`, `app/models.py`, `app/schemas.py`, and `services/guardrails.py` against the live schema at `data/prompt_registry.db`.

**Scope:** Inventory only. Standards tagging is Block 2 and 3. Retention review for degenerate dimensions is Block 3.5. Phase allocation is Block 4. No conclusions about which dimensions survive, which retire, or which phase each belongs to are drawn here.

### The 17 dimensions

| # | ID | Name | What the code checks | Input required | Migration state |
|---|---|---|---|---|---|
| 1 | REG_D1 | Regulatory Compliance | Whether the prompt text names a regulatory framework and states jurisdictional scope | Prompt text only | Old fallback — guardrail clause in `REGULATORY_COMPONENTS["REG_D1"]` |
| 2 | REG_D2 | Transparency | Whether the prompt declares AI-generated output, marks it advisory, states limitations, and does not suppress AI identity | Prompt text only | **New pattern — `instructional_text` on `ScoringDimension`, synced at startup. The only dimension migrated.** |
| 3 | REG_D3 | Data Minimisation | Whether the prompt limits data to what is necessary, declares retention prohibition, and names a legal basis for personal data | Prompt text only | Old fallback — `REGULATORY_COMPONENTS["REG_D3"]` |
| 4 | REG_D4 | Audit Trail | Whether reasoning is traceable, output is storable as an audit record, and a named human is accountable | Prompt text only | Old fallback — `REGULATORY_COMPONENTS["REG_D4"]` |
| 5 | REG_D5 | Operational Resilience | Whether the prompt declares failure modes, a fallback, and avoids a single point of failure | Prompt text only | Old fallback — `REGULATORY_COMPONENTS["REG_D5"]` |
| 6 | REG_D6 | Outsourcing Controls | Whether the prompt documents data residency, sub-processing restrictions, and third-party audit rights | Prompt text only | Old fallback — `REGULATORY_COMPONENTS["REG_D6"]` |
| 7 | OWASP_LLM01 | Prompt Injection Resistance | Whether the prompt wraps user content in delimiters, instructs the AI to treat it as data only, and defines an escalation path | Prompt text only | **Degenerate fallback — scored only, no clause injected** |
| 8 | OWASP_LLM02 | Sensitive Information Disclosure | Whether the AI is instructed not to reproduce system prompt contents or leak configuration | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 9 | OWASP_LLM06 | Excessive Agency | Whether the scope of AI actions is explicitly limited and downstream-system instruction is prevented | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 10 | OWASP_LLM08 | Overreliance | Whether the output is explicitly advisory, confidence is declared, and human review is required before action | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 11 | OWASP_LLM09 | Misinformation | Whether the AI is instructed not to fabricate regulatory references and to declare uncertainty explicitly | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 12 | NIST_GOVERN_1 | Governance Accountability | Whether named owner, approver, and review cadence are all declared | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 13 | NIST_MAP_1 | Context and Limitations | Whether context of use, intended user base, and known limitations are all declared | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 14 | NIST_MEASURE_1 | Output Quality Measurement | Whether the prompt defines how output quality will be measured and monitored over time | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 15 | NIST_MANAGE_1 | Decommission Trigger | Whether the prompt declares a decommission or review trigger | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 16 | ISO42001_6_1 | Risk Assessment | Whether a risk assessment covering impact on individuals, operational risk, and mitigants is present | Prompt text only | **Degenerate fallback — scored only, no clause** |
| 17 | ISO42001_8_4 | Data Quality and Bias | Whether data sources, data quality requirements, and bias considerations are declared | Prompt text only | **Degenerate fallback — scored only, no clause** |

### Framework distribution

| Framework | Count | Current engine weight |
|---|---|---|
| Regulatory (REG) | 6 | 40% |
| OWASP LLM | 5 | 30% |
| NIST AI RMF | 4 | 20% |
| ISO/IEC 42001 | 2 | 10% |
| **Total** | **17** | **100%** |

Composite weights are hard-coded at `services/compliance_engine.py` lines 32–37.

### Findings

Five findings surfaced during the inventory. All are implications for downstream blocks rather than conclusions to act on in Block 1.

**F1 — "Migration" is two jobs, not one.** Of the sixteen unmigrated dimensions, five (REG_D1, D3, D4, D5, D6) have existing guardrail text in `services/prompt_components.py` that needs to be moved from code to config. The other eleven (OWASP, NIST, ISO) are a degenerate case: they are scored but inject nothing — there is no existing text to migrate. The migration task for those eleven is to **write** instructional text for the first time, not to move it — or to retire them. That retention decision is Block 3.5.

**F2 — Scoring input is uniform today; the schema anticipates otherwise.** Every dimension currently receives only `version.prompt_text` at scoring time (see `services/compliance_engine.py:278-284`). But `ScoringDimension` already carries `applies_if`, `applies_to_types`, `tier`, and `tier2_trigger` columns. The column shape for configuration-driven applicability already exists — the engine just ignores it. Block 6 (schema design) does not need to invent a new applicability mechanism; it needs to specify one that the engine honours.

**F3 — The `deployment_target` field is already being split to support runtime context.** `prompts.deployment_target` is a single `VARCHAR NOT NULL` marked deprecated at `app/models.py:139-141`, being split into `ai_platform` and `output_destination` on the same table. These two concepts map directly to the Deployment-phase fields defined in the wiki (invocation context, output handling). The data model has been reaching for three-phase thinking; the engine has not caught up. The Deployment workflow in Blocks 12–16 formalises a half-finished migration rather than introducing a new concept.

**F4 — No `Client` entity in the schema.** There is no `clients` table. Any deployment-context concept in the framework that presumes a client dimension (for example, client-specific applicability rules or client-scoped configuration) would need to introduce that entity. Noted for Block 6; parked for Phase 3 if not strictly required.

**F5 — Empty live database; refactor risk is lower than assumed.** `data/prompt_registry.db` contains 0 rows in `prompts`, `briefs`, and `prompt_versions`. There is one row in `audit_log` and no live state elsewhere. Block 7 (schema migration) does not need to reconcile or preserve production data. This materially reduces the risk profile of the single highest-risk block in the plan.

### Implications for subsequent blocks

- **Block 2 (OWASP tagging)** and **Block 3 (ISO/NIST tagging)** — proceed as planned. The inventory is ready.
- **Block 3.5 (new — retention review for degenerate dimensions)** — before Block 4 allocates, the 11 OWASP / NIST / ISO dimensions that have no existing instructional text are reviewed for retention. Each is either kept (with a commitment to write new text in Block 4), relabelled, or retired. This keeps allocation honest: the 22-block plan does not quietly inherit dimensions that never did anything.
- **Block 4 (dimension allocation)** — proceeds on the surviving set from Block 3.5. Output format (`seed/dimensions.yml`) accommodates two migration shapes: existing-text-to-move (5 dimensions, subject to rewrite) and new-text-to-write (survivors from Block 3.5). When allocating, the REG guardrail clauses in `REGULATORY_COMPONENTS` are reviewed against the wiki framing of artefact-level controls; text either carries forward verbatim, is rewritten, or is replaced.
- **Block 6 (schema design)** — confirm that `applies_if` / `tier` / `tier2_trigger` are the applicability primitives to honour rather than replace. Confirm whether `Client` entity is introduced now, deferred, or considered out of scope.
- **Block 7 (schema migration)** — empty database; treat as a fresh-schema migration rather than a reconciliation. Meaningful scope reduction.
- **Block 9 (Build engine rewrite)** — the 40/30/20/10 composite weights are hard-coded and violate the configuration-first principle. Weights move to config as part of Block 9.
- **Block 12 (Deployment form spec)** — the `ai_platform` and `output_destination` split is the existing seam. The Deployment form fields build on that, not around it.

### Plan adjustment — new Block 3.5

The 22-block plan adds one block between the existing Blocks 3 and 4.

**Block 3.5 — Retention review for degenerate dimensions.** Tier A, chat work. The 11 dimensions with no existing instructional text (OWASP_LLM01, LLM02, LLM06, LLM08, LLM09; NIST_GOVERN_1, MAP_1, MEASURE_1, MANAGE_1; ISO42001_6_1, 8_4) are each reviewed for retention, relabelling, or retirement. Output is a short decision record appended to `ARCHITECTURE.md` — ID, decision, rationale. Block 4 then allocates the surviving set.
*Done when:* each of the 11 has a recorded decision and the surviving set is named.

The total block count becomes 23, not 22. `REFACTOR_PLAN.md` is not updated in this commit — the amendment will be made alongside Block 3.5's output so that plan and architecture land together.

---

*Block 1 complete. Block 2 (OWASP tagging) follows, then Block 3 (ISO/NIST), then new Block 3.5 (retention review), then Block 4 (allocation).*
