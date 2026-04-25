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

## Block 2 — OWASP LLM Top 10 tagging

**Status:** Complete. Source: OWASP LLM Top 10, 2025 edition. The 2025 list is taken as canonical because the 2023 list — which the existing dimension IDs partially follow — has been retired by OWASP. A migration note is recorded below.

**Scope:** Tag each of the ten current entries to the phase where the control most naturally lives: Build (artefact-level, can be assessed by reading prompt text alone), Deployment (depends on runtime context — what calls the prompt, what data flows in, where output goes), Operation (depends on continuous behaviour and surveillance), or Vendor (concerns the model provider's pipeline and not directly assessable at our layer).

| # | OWASP 2025 | Title | Phase | Rationale |
|---|---|---|---|---|
| 1 | LLM01:2025 | Prompt Injection | **Build + Deployment** | Build: the prompt's own injection-resistance instructions (delimiter discipline, treat-user-content-as-data) are artefact-level. Deployment: whether the runtime actually wraps user content correctly, sanitises tool inputs, and enforces the escalation path is a property of the calling system. |
| 2 | LLM02:2025 | Sensitive Information Disclosure | **Build + Deployment** | Build: the prompt instructs not to echo system prompt or configuration. Deployment: what data the runtime is allowed to feed into the prompt (PII redaction, scoping rules) is the deployment-side half. |
| 3 | LLM03:2025 | Supply Chain | **Vendor** | Concerns model lineage, training data integrity, fine-tune providers. Outside the registry's authority. Recorded; not graded. |
| 4 | LLM04:2025 | Data and Model Poisoning | **Vendor** | Same. Concerns the model provider. Not directly assessable from prompt text or deployment configuration. |
| 5 | LLM05:2025 | Improper Output Handling | **Deployment** | Whether downstream systems receive raw model output without escaping, parse it as code, or render it unsafely is a deployment-side property. The prompt cannot prevent unsafe handling by its caller. |
| 6 | LLM06:2025 | Excessive Agency | **Build + Deployment** | Build: the prompt scopes what the AI is permitted to do. Deployment: tool grants, write permissions, and downstream effect surfaces are runtime configuration. Both halves matter. |
| 7 | LLM07:2025 | System Prompt Leakage | **Build** | Whether the prompt text itself is structured to resist leakage (no secrets in system prompt, instructions not to echo role/instructions) is artefact-level. |
| 8 | LLM08:2025 | Vector and Embedding Weaknesses | **Deployment** | Concerns retrieval pipelines: what is in the vector store, who can query it, how matches are ranked. Property of the deployment, not of the prompt. |
| 9 | LLM09:2025 | Misinformation | **Build + Operation** | Build: the prompt instructs the model to declare uncertainty, not fabricate references, mark output advisory. Operation: detecting that a deployed prompt is in fact producing misinformation requires post-hoc surveillance over real outputs. |
| 10 | LLM10:2025 | Unbounded Consumption | **Deployment** | Token caps, rate limits, cost ceilings are deployment configuration, not prompt-text properties. |

### 2023-to-2025 migration note

The existing dimension catalogue uses a mix of 2023 and 2025 OWASP numbering, which is why some IDs do not match the table above:

- `OWASP_LLM01` (Prompt Injection Resistance) — aligns with both 2023 and 2025 LLM01. **Stable.**
- `OWASP_LLM02` (Sensitive Information Disclosure) — that is **2025 LLM02** but was **2023 LLM06**. The current ID matches the 2025 numbering. **Stable.**
- `OWASP_LLM06` (Excessive Agency) — that is **2025 LLM06** and was **2023 LLM08**. ID matches 2025. **Stable.**
- `OWASP_LLM08` (Overreliance) — Overreliance was **2023 LLM09**; in the 2025 list it has been folded into **LLM09 Misinformation** as a related risk rather than a standalone entry. The existing `OWASP_LLM08` ID does not correspond to anything in 2025. **Action: rename or retire in Block 4.**
- `OWASP_LLM09` (Misinformation) — that is **2025 LLM09**. **Stable.**

The renumbering matters because the `OWASP_LLM08` ID currently refers to a concept (Overreliance) that the standard has merged into a sibling concept (Misinformation). Block 4 must decide whether to retire `OWASP_LLM08`, fold its instructional text into `OWASP_LLM09`, or relabel under a new ID that maps cleanly to 2025.

### Tagging summary by phase

- **Build:** LLM01 (shared), LLM02 (shared), LLM06 (shared), LLM07, LLM09 (shared)
- **Deployment:** LLM01 (shared), LLM02 (shared), LLM05, LLM06 (shared), LLM08, LLM10
- **Operation:** LLM09 (shared)
- **Vendor (out of scope for grading):** LLM03, LLM04

LLM01, LLM02, LLM06, LLM09 each split across phases. Block 4 must allocate each split into a primary phase rather than duplicating dimensions across phases — duplication is what the configuration-first principle disallows. The phase allocation follows the heuristic: "where is the prompt-text-only check most informative?" — that places all four primarily in Build, with Deployment-side enforcement deferred to a separate Deployment-phase dimension if the Deployment compliance engine surfaces a real gap during Block 11 or Block 15 smoke testing.

---

## Block 3 — ISO 42001 and NIST AI RMF tagging

**Status:** Complete (orientation pass, not full read). Source: ISO/IEC 42001:2023 Annex A control structure and NIST AI RMF 1.0 core functions. Both are tagged at the level the plan requires — orientation, not exhaustive.

### ISO/IEC 42001 Annex A controls

ISO 42001 Annex A is organised under nine objectives (A.2–A.10). The existing catalogue has two dimensions tagged ISO42001 (`ISO42001_6_1` Risk Assessment, `ISO42001_8_4` Data Quality and Bias). The numbering does not directly correspond to Annex A's structure (which uses A.x.y format, not 6.1 / 8.4); these IDs appear to reference clauses of the main standard body rather than Annex A controls. Block 4 must reconcile this — the IDs should match whichever section the firm intends to defend on.

| Annex A objective | Phase | Rationale |
|---|---|---|
| A.2 Policies related to AI | **Operation** (organisation-level) | Policy existence and review cadence are operational governance. Not a per-prompt artefact-level check. |
| A.3 Internal organization (roles & responsibilities) | **Build + Operation** | Build: prompt declares its accountable owner/reviewer. Operation: the firm tracks that those people exist and remain assigned. |
| A.4 Resources (data, tooling, human, computational) | **Deployment** | What the deployed AI system is provisioned with — relevant at Deployment, not in the prompt artefact. |
| A.5 Assessing impacts of AI systems | **Build + Deployment** | Build: impact assessment per prompt. Deployment: re-assessed when context changes. |
| A.6 AI system life cycle | **All three phases** | This is in fact what the registry's three-phase model is implementing. Not a single-phase tag. |
| A.7 Data for AI systems | **Deployment** | What data flows to the deployed system. Not a prompt-text property. |
| A.8 Information for interested parties of AI systems | **Build + Operation** | Build: prompt declares what the system is and is not. Operation: external disclosures kept current. |
| A.9 Use of AI systems | **Operation** | Continuous monitoring of intended-use compliance. |
| A.10 Third-party and customer relationships | **Deployment** | Outsourcing, sub-processing, residency are deployment-time configuration. |

The existing `ISO42001_6_1` (Risk Assessment) maps to **A.5 Assessing impacts of AI systems** — Build phase primarily. The existing `ISO42001_8_4` (Data Quality and Bias) maps to **A.7 Data for AI systems** — Deployment phase. Block 4 will retag with these references, retiring the unconventional `_6_1` / `_8_4` IDs in favour of names that bind to Annex A.

### NIST AI RMF — orientation

The NIST AI RMF 1.0 has four core functions: GOVERN, MAP, MEASURE, MANAGE. The existing catalogue has four dimensions, one tagged to each function (`NIST_GOVERN_1`, `NIST_MAP_1`, `NIST_MEASURE_1`, `NIST_MANAGE_1`). Each refers to the function rather than a specific subcategory.

| RMF function | What it covers | Phase | Rationale |
|---|---|---|---|
| GOVERN | Policies, roles, accountability, risk culture, transparency commitments | **Operation** (org-level) with Build hook | The named-owner / named-reviewer / cadence triple is the Build hook into the org-level GOVERN function. |
| MAP | Context, intended use, limitations, stakeholders, impacts | **Build** | Per-prompt context and limitations are an artefact-level property. Aligns with Build. |
| MEASURE | Quality metrics, evaluation methods, ongoing measurement | **Operation** | Continuous metric collection is operational. The Build phase can declare what will be measured, but the measurement itself runs in Operation. |
| MANAGE | Risk treatment, prioritisation, decommission, incident response | **Operation** primarily, with Build declaration | Decommission triggers and management policies are operational; the Build artefact may declare the trigger condition. |

The existing tagging is therefore consistent with this orientation: `NIST_GOVERN_1` is Build-side accountability declaration that hooks org-level GOVERN; `NIST_MAP_1` is Build-side context-and-limitations; `NIST_MEASURE_1` is the Build-side declaration of what Operation will measure; `NIST_MANAGE_1` is the Build-side declaration of the Operation-side decommission trigger.

This produces a useful pattern: **most NIST and ISO controls are operational, but each has a Build-side declaration the prompt artefact must contain so that the operational machinery has something to act on.** That is the basis on which Block 4 places the NIST and ISO dimensions in Build despite the standards themselves being mostly operational — they are declarations, not the operational acts.

### Tagging summary by phase

- **Build (declarations):** ISO A.5, ISO A.8 (partial), NIST MAP, NIST GOVERN-decl, NIST MANAGE-decl, NIST MEASURE-decl
- **Deployment (runtime configuration):** ISO A.4, ISO A.7, ISO A.10, ISO A.5 (re-assess on context change)
- **Operation (continuous):** ISO A.2, ISO A.9, NIST GOVERN-org, NIST MEASURE-runtime, NIST MANAGE-runtime
- **All three:** ISO A.6 (lifecycle — the registry's whole job)

---

## Block 3.5 — Retention review for degenerate dimensions

**Status:** Complete. The 11 dimensions with no existing instructional text are reviewed below. Each has one of three decisions: **keep** (write new text in Block 4), **fold** (merge into a sibling), or **retire**.

| # | ID | Decision | Rationale |
|---|---|---|---|
| 1 | OWASP_LLM01 | **Keep** | Prompt-injection resistance is a hard Build-phase requirement. Text to be written: delimiter wrapping rule, treat-user-content-as-data rule, escalation path. |
| 2 | OWASP_LLM02 | **Keep** | Sensitive-information-disclosure resistance is a Build-phase requirement. Text: do-not-echo-system-prompt rule, do-not-leak-configuration rule. |
| 3 | OWASP_LLM06 | **Keep** | Excessive-agency control is a Build-phase requirement. Text: scope-of-action limit, no-instruction-to-downstream-systems rule. |
| 4 | OWASP_LLM08 (Overreliance) | **Fold into LLM09** | OWASP 2025 has merged Overreliance into LLM09 Misinformation. Retaining a standalone Overreliance dimension creates drift from the standard. The advisory-output / declared-confidence / human-review elements move into the LLM09 instructional text. The ID `OWASP_LLM08` is retired in Block 4. |
| 5 | OWASP_LLM09 | **Keep (expanded)** | Misinformation control. Text: do-not-fabricate-references, declare-uncertainty, mark-output-advisory, require-human-review. The last three are folded in from former LLM08. |
| 6 | NIST_GOVERN_1 | **Keep, retag** | Governance accountability declaration. Retag from `NIST_GOVERN_1` to a name that references the actual NIST subcategory: GOVERN 1.1 (governance roles defined). Text: named owner, named approver, declared review cadence. |
| 7 | NIST_MAP_1 | **Keep, retag** | Context-and-limitations declaration. Retag to MAP 1.1 (context defined). Text: context-of-use statement, intended-user-base, declared known-limitations. |
| 8 | NIST_MEASURE_1 | **Keep, retag** | Output-quality measurement declaration. Retag to MEASURE 2.3 (system performance regularly evaluated). Text: how output quality will be measured, by whom, on what cadence. |
| 9 | NIST_MANAGE_1 | **Keep, retag** | Decommission-trigger declaration. Retag to MANAGE 2.4 (mechanisms to supersede, deactivate, or decommission systems). Text: explicit decommission or review trigger condition. |
| 10 | ISO42001_6_1 | **Keep, retag** | Risk-assessment declaration. Retag to **ISO42001 A.5.2** (AI system impact assessment). Text: impact-on-individuals, operational-risk, mitigants. |
| 11 | ISO42001_8_4 | **Move to Deployment, retag** | Data-quality-and-bias is fundamentally a Deployment-phase concern (what data flows in). Retag to **ISO42001 A.7** (Data for AI systems). The Build-side declaration is "data sources, data quality requirements, bias considerations declared"; the Deployment-side check is whether those declarations match the runtime data flow. Block 4 places this at Build (declaration) and notes the Deployment counterpart for Block 14. |

### Surviving set after Block 3.5

**16 dimensions survive** out of the original 17. One retired: `OWASP_LLM08` (Overreliance), folded into `OWASP_LLM09`.

The 16 split into:
- **5 with text to migrate** (REG_D1, D3, D4, D5, D6 — already had guardrail text in `REGULATORY_COMPONENTS`)
- **10 with text to write fresh** (the 10 above with **Keep** or **Keep + retag** decisions)
- **1 absorbed** the former LLM08 content (LLM09)

Many of the 10 will be retagged in Block 4 to bind to specific subcategory references rather than the generic `_GOVERN_1`, `_6_1`, `_8_4` placeholders.

---

## Block 4 — Dimension allocation

**Status:** Complete. Each surviving dimension is allocated to **Build**, **Deployment**, or **Operation**, labelled with its standard reference, and emitted as seed data at `seed/dimensions.yml`. A companion `seed/standards.yml` defines the standards catalogue the dimensions reference.

The allocation follows the principle established in Block 3: **declarations live in Build; runtime checks live in Deployment; continuous surveillance lives in Operation.** Most dimensions are Build declarations because the prompt-text-only scoring input that the legacy engine uses is, by definition, an artefact check. A dimension that requires runtime context to score must move to Deployment in subsequent blocks, where the Deployment compliance engine receives a `deployment_record`, not a prompt.

### Allocation table

| Code (new) | Title | Phase | Standard reference | Migration shape |
|---|---|---|---|---|
| REG_REGULATORY_FRAMEWORK | Regulatory framework named with jurisdictional scope | **Build** | EU AI Act, FCA SYSC 8 (proxy reference) | Migrate text from `REGULATORY_COMPONENTS["REG_D1"]` |
| REG_TRANSPARENCY | AI-generated output declared, advisory, with limitations | **Build** | EU AI Act Art. 52 (transparency) | Already migrated (was REG_D2) |
| REG_DATA_MINIMISATION | Data limited to necessary, retention prohibited, legal basis named | **Build** | UK GDPR Art. 5(1)(c) | Migrate text from `REGULATORY_COMPONENTS["REG_D3"]` |
| REG_AUDIT_TRAIL | Reasoning traceable, output storable, accountable human named | **Build** | FCA SYSC 9 | Migrate text from `REGULATORY_COMPONENTS["REG_D4"]` |
| REG_OPERATIONAL_RESILIENCE | Failure modes, fallback, no single point of failure | **Build** | PRA SS1/21 (Operational Resilience) | Migrate text from `REGULATORY_COMPONENTS["REG_D5"]` |
| REG_OUTSOURCING_CONTROLS | Data residency, sub-processing restrictions, third-party audit rights | **Deployment** | EBA Outsourcing Guidelines | Migrate text from `REGULATORY_COMPONENTS["REG_D6"]` (declaration carries forward as a Build hint, but the binding check is at Deployment) |
| OWASP_PROMPT_INJECTION | Delimiter discipline, user-content-as-data, escalation path | **Build** | OWASP LLM01:2025 | Write fresh |
| OWASP_SENSITIVE_INFO | Do not echo system prompt; do not leak configuration | **Build** | OWASP LLM02:2025 | Write fresh |
| OWASP_EXCESSIVE_AGENCY | Scope of action limited; no instruction to downstream systems | **Build** | OWASP LLM06:2025 | Write fresh |
| OWASP_MISINFORMATION | No fabrication; declare uncertainty; advisory; require human review | **Build** | OWASP LLM09:2025 | Write fresh (absorbs former LLM08 Overreliance) |
| OWASP_SYSTEM_PROMPT_LEAKAGE | Prompt structured to resist role/instruction echo | **Build** | OWASP LLM07:2025 | Write fresh — new dimension, surfaced by Block 2 |
| NIST_GOVERN_ROLES | Named owner, named approver, declared review cadence | **Build** | NIST AI RMF GOVERN 1.1 | Write fresh |
| NIST_MAP_CONTEXT | Context of use, intended user base, declared limitations | **Build** | NIST AI RMF MAP 1.1 | Write fresh |
| NIST_MEASURE_QUALITY | How output quality will be measured, by whom, cadence | **Build** | NIST AI RMF MEASURE 2.3 | Write fresh |
| NIST_MANAGE_DECOMMISSION | Explicit decommission or review trigger condition | **Build** | NIST AI RMF MANAGE 2.4 | Write fresh |
| ISO42001_IMPACT_ASSESSMENT | Impact on individuals, operational risk, mitigants | **Build** | ISO/IEC 42001 A.5.2 | Write fresh |
| ISO42001_DATA_GOVERNANCE | Data sources, data quality requirements, bias considerations | **Build** (declaration) + **Deployment** (runtime data flow check) | ISO/IEC 42001 A.7 | Write fresh; Deployment counterpart deferred to Block 14 |

### Counts and weightings

- **Build:** 16 dimensions (15 declarations + 1 new from Block 2 — OWASP_SYSTEM_PROMPT_LEAKAGE)
- **Deployment:** 1 dimension (REG_OUTSOURCING_CONTROLS) plus the Deployment side of ISO42001_DATA_GOVERNANCE
- **Operation:** 0 dimensions yet — Operation phase introduces its own (review cadence, incident logging, retirement triggers) in Block 17

The legacy 40/30/20/10 weighting (REG / OWASP / NIST / ISO) is retired with the legacy code. Per-phase weights become configuration in `seed/standards.yml` so they can be tuned without code change. Block 9 will read the weights from config rather than constants.

### Output files

- `seed/dimensions.yml` — full dimension catalogue
- `seed/standards.yml` — standards catalogue with references
- `seed/phases.yml` — phase definitions
- `seed/gates.yml` — gate definitions per phase

These four files together are the configuration the Phase 2 schema seeds from. Block 7 will load them.

---

## Block 5 — Architecture note

**Status:** Complete. The architecture in one page.

### The model

A prompt is an artefact that moves through three phases. Each phase has its own purpose, its own dimension subset, its own compliance grade, and its own approval gate. Phases do not collapse into a single compliance pass; each gate is independent.

```
   ┌──────────┐    Build      ┌──────────┐  Deployment   ┌──────────┐  Operation
   │  Brief   │────gate───→   │  Build   │────gate───→   │ Deployed │────cadence──→
   │ (input)  │               │ artefact │               │ capability│
   └──────────┘               └──────────┘               └──────────┘
                                  │                          │            │
                              dimensions:                dimensions:   dimensions:
                              artefact-level             runtime       continuous
                              checks                     context       surveillance
                              (16 dims)                  (1+)          (TBD Block 17)
```

### The schema sketch

The configuration-first principle says behaviour lives in data. The schema implements that: code reads tables, executes generically, never branches on dimension or standard identity.

Tables that hold configuration (read-mostly, seeded from YAML, audited on change):

- `standards` — OWASP / ISO 42001 / NIST AI RMF / regulatory references with versioned clause lookups
- `dimensions` — every dimension's name, phase, standard reference, applicability rule, scoring rubric, instructional text
- `phases` — the three phase definitions with weights and approval rules
- `gates` — gate rules per phase: who can approve, what conditions must hold
- `applicability_rules` — structured rules ("applies if input_type is document", "applies if risk_tier ≥ 2") evaluated by a generic engine
- `scoring_rubrics` — prompt templates that the engine sends to the scoring model
- `form_fields` — Brief Builder and Deployment form field definitions, types, validation, display rules

Tables that hold records (write-heavy, audit log, the journal of what happened):

- `prompts` — existing
- `prompt_versions` — existing
- `compliance_runs` — extended to carry phase identifier
- `deployment_records` — new, captures runtime context per deployed prompt
- `operation_records` — new, captures lifecycle state, review dates, incident log, retirement state
- `gate_decisions` — new, named approver / decision / rationale per gate
- `audit_log` — existing, extended

### How a prompt moves left to right

**Build.** A brief becomes a prompt. The Build engine reads `phases.build.dimensions` from config, applies each dimension's `applicability_rule` against the prompt's metadata (prompt type, input type, risk tier), runs the surviving dimensions through their `scoring_rubric`, aggregates per the configured weights, and writes a Build `compliance_run`. The Build `gate` rule decides whether the prompt may proceed.

**Deployment.** A Build-approved prompt becomes a deployed capability. The Deployment form (whose fields are seeded from `form_fields`) captures runtime context: invocation context, input sources, output handling, monitoring cadence, runtime owner, incident response, change management. The Deployment engine — the *same* engine code as Build, called with a different phase parameter — reads `phases.deployment.dimensions`, applies them to the `deployment_record`, aggregates, writes a Deployment `compliance_run`, fires the Deployment gate.

**Operation.** A Deployment-approved capability has an `operation_record` created at the moment of approval. The Operation engine runs on cadence (also config), reads `phases.operation.dimensions`, runs them against `operation_record` state and accumulated incident data, fires retirement triggers when conditions hold.

### The four invariants

1. **No dimension is named in code outside seed loaders.** The engine does not know about REG_D2 or OWASP_LLM01. It loops over a config-driven list.
2. **No phase is hard-coded into a dimension.** A dimension records its phase as a column value, not as a class hierarchy.
3. **No standard reference is stored in code.** OWASP, ISO, NIST clauses live in `standards`. UI joins.
4. **No gate rule is conditional on a specific dimension code.** Gate rules read `min_grade` and `must_pass_dimensions` from `gates`, not `if d == "REG_D1"`.

The four invariants are testable. The test strategy in Block 9 onward enforces them: any test that hard-codes a dimension code is a regression and gets rewritten to fixture-based dimensions.

### What the refactor does *not* touch

- Brief Builder question text — Phase 3
- The variable resolver — already generic
- Title feature — orthogonal
- Audit log structure — extended, not replaced

The refactor is the engine and the schema. Surrounding orchestration code stays.

---

*Phase 0 complete. Phase 1 (schema) follows: Block 6 (SCHEMA_V2.md), Block 7 (migration + seed).*
