# Step 1 as Topic Checklist — Design Document

**Scope:** Extraction prompt type only. Other types (Classification, Summarisation, Comparison, Analysis, Comms, Governance, Risk Review) extend the same pattern in follow-up design sessions.

**Status:** Design only, pre-implementation. Incorporates revisions from review dated post-19 April.

---

## Part A — Reconnaissance findings

### A1. Current Step 1 data model and flow

**Brief entity (`app/models.py:332-357`):** `brief_id`, `title` (nullable), `status`, `quality_score`, `step_progress`, `client_name`, `business_owner_name`, `business_owner_role`, `brief_builder_id`, `interviewer_id`, `step_answers` (JSON TEXT, defaults `"{}"`), `selected_guardrails` (JSON TEXT), `restructured_brief`, `created_at`, `updated_at`, `submitted_at`, `resulting_prompt_id`.

**Frontend state (`brief.js:16-17`):** `{ purpose, inputType, outputType, audience, constraints[], selectedGuardrails[], clientName, ownerName, ownerRole, skipped[] }`. Only `state.purpose` is prose; the rest are already structured picks (Steps 2-6).

**Flow (source of `brief_text` into the generator):**

1. User types in Step 1 textarea → `state.purpose`.
2. Steps 2-6 populate `state.inputType`, `state.outputType`, `state.audience`, `state.constraints`, `state.selectedGuardrails`.
3. `_briefReview()` → `loadRestructuredBrief()` → POSTs `buildBriefText()` to `/prompts/briefs/restructure`. `buildBriefText()` (`brief.js:451-465`) concatenates state.* fields into a labelled-line blob.
4. Returns `{restructured, title}`, user reviews on review screen (edits both fields in place).
5. `_briefSend()` PATCHes `{title, restructured_brief}` to `/briefs/{id}`, POSTs `/complete`, navigates to generator. Stashes `restructuredBrief` as `window._briefTextForGenerate`; sets DOM values for `gen-title`, `gen-type`, `gen-input`, `gen-output` via `setTimeout`.
6. User clicks Generate with AI → `genAI()` POSTs `/prompts/generate` with the brief text + title + type + etc.

**Key observation:** The Brief Builder's structured fields (`state.inputType`, `state.outputType`) are already picked by the user in Steps 2-3, AND also described in prose in Step 1's purpose textarea. The user reconciles this twice. Prompt Type, Risk Tier, Deployment Target are not captured at all — they're inferred at the generator screen.

### A2. Generator screen fields (`static/views/generator.js:12-70`)

| # | Field | HTML | Options | Pre-filled from brief? |
|---|---|---|---|---|
| 1 | Title | `#gen-title` text input | free text | ✓ (from `brief.title`, Slot T1) |
| 2 | Prompt Type | `#gen-type` select | 8 PromptType literals | ✓ (via `typeMap` keyed on Output Type) |
| 3 | Deployment Target | `#gen-deploy` select | Claude / MS Copilot Declarative / MS Copilot Custom Engine / OpenAI / Multi-model / Other | ✗ defaults "Claude" |
| 4 | Risk Tier | `#gen-risk` select | Minimal / Limited / High / Prohibited | ✗ defaults "Limited" |
| 5 | Input Type | `#gen-input` select | 8 options matching `INPUT_OPTIONS` | ✓ from `state.inputType` |
| 6 | Output Type | `#gen-output` select | 9 options matching `OUTPUT_OPTIONS` | ✓ from `state.outputType` |
| 7 | Prompt Text | `#gen-text` textarea | — | populated by Generate-with-AI click |
| 8 | Change Summary | `#gen-summary` text | free text | ✗ user fills |

**Inferred-and-hidden linkage:** `_briefSend`'s `typeMap` quietly maps Output Type → Prompt Type. User sees Prompt Type pre-populated on the generator screen but was never asked for it directly.

**Field naming defect (surfaced during review):** `deployment_target` conflates two distinct things — *which AI platform runs the prompt* (Claude, MS Copilot, OpenAI…) and *where the output goes* (Simcorp, Temenos, a downstream pipeline…). These are orthogonal and need separate fields. See revision in Part B4.

### A3. prompt_type taxonomy

**`PromptType` literal (`app/schemas.py:7-16`):** `Governance | Analysis | Comms | Classification | Summarisation | Extraction | Comparison | Risk Review`.

**`RiskTier` literal:** `Minimal | Limited | High | Prohibited`.

**Where `prompt_type` drives behaviour:** `services/prompt_components.py` `TEMPLATES` map. For `"Extraction"`:

```python
"Extraction": {
    "name": "Data Extraction",
    "description": "Structured data extraction with confidence scoring",
    "input_handler": "Document or report",
    "output_handler": "Data extraction",
    "regulatory_codes": ["REG_D1", "REG_D4"],
    "behaviour_codes": ["COMP-BEH-01", "COMP-BEH-02"],
    "output_example": None,
},
```

`prompt_type` selects input handler, output handler, mandatory regulatory guardrails (D1 Human Oversight, D4 Audit Trail), and behaviour guardrails (Hallucination prevention, Uncertainty handling). Load-bearing — changing the type changes the generated prompt's structure significantly.

### A4. validate_brief scope (post-today's redesign)

Whole-brief evaluation. `ValidateBriefRequest = { description: str, conversation_history: list[ConversationEntry] }`. Returns `{ tier, accepted, question?, options?, free_text_placeholder?, suggestion?, suggested_addition? }`. Single tier result per call, conflating every gap into the "weakest element" framework.

**For per-topic evaluation, the request shape needs:** `topic_id: str`, plus the user's current answer for that topic, plus the current answers for sibling topics (Claude needs cross-reference context). The response stays the same shape conceptually (state + probe), but the state vocabulary shifts from `{1,2,3}` tiers to `{red, amber, green}` colours.

---

## Part B — Design

### B1. Topic list for Extraction

Eleven topics (five structured including the new AI-platform topic, plus five prose, plus Prompt Type as gate). Structured topics are greenable on pick.

**Structured topics** (metadata — flow to generator screen fields):

| # | Topic | Options | Generator field |
|---|---|---|---|
| 1 | **Prompt Type** | The 8 PromptType values | `prompt_type` |
| 2 | **Source document type** | Prospectus, Policy, Circular, Regulatory filing, Report, Contract, Email thread, Form responses, Data table, Free text, Other+free-text | maps to `input_type` via translation |
| 3 | **Output format** | JSON object, Table/CSV, Markdown extraction report, Flag report, Data extraction payload, Other | maps to `output_type` |
| 4 | **Target system (where the output goes)** | Simcorp, Temenos, Charles River, Bloomberg AIM, Murex, Internal spreadsheet, Downstream AI/pipeline, Advisory only (no system), Other+free-text | maps to **new** `output_destination` field |
| 4b | **AI platform (what runs the prompt)** | Claude, MS Copilot — Declarative, MS Copilot — Custom Engine, OpenAI, Multi-model, Other | maps to **new** `ai_platform` field (defaults to Claude; quick pick) |
| 5 | **Risk tier** | Minimal, Limited, High, Prohibited | maps to `risk_tier` |

**Prose topics** (domain content — concatenate into the brief text sent to `/generate`):

| # | Topic | What Claude coaches on |
|---|---|---|
| 6 | **Data points to extract** | Name each field, its expected type, and roughly where it appears in the source. Minimum threshold: ≥1 field with name + type. |
| 7 | **Per-field format / normalisation** | For each extracted field, how the output should be normalised (time-zone form, decimal format, date format, unit conventions). Required if output format is structured (JSON/Table). |
| 8 | **Null / missing handling** | Explicit policy for fields not found in the source: null + low confidence, explicit "not-found" marker, skip-record, error. |
| 9 | **Confidence and traceability** | Whether the prompt emits per-field confidence and page/section references for audit. |
| 10 | **Error / exception modes** | Partial document, malformed source, conflicting values across pages. At least one mode explicitly handled. |

### B2. Per-topic definitions

Format: Name · Interaction · Options or Coaching · RAG rules · Mapping.

---

**Topic 1 — Prompt Type**
- Interaction: structured single-select.
- Options: the 8 PromptType literals.
- RAG: red until picked; green once picked. No amber.
- Mapping: → `generator.prompt_type`. Also switches `TEMPLATES` behaviour server-side.
- Notes: First topic the user should pick — it defines which topic list applies. Cold start CTA points here.

**Topic 2 — Source document type**
- Interaction: structured single-select (multi-select allowed if prompt processes mixed sources).
- Options: Prospectus / Policy / Circular / Regulatory filing / Report / Contract / Email thread / Form responses / Data table / Free text / Other + free-text.
- RAG: red until picked. Green on selection. Amber if "Other" without free-text follow-up.
- Mapping: UI-layer domain term → `generator.input_type` via a translation map (Prospectus → "Document or report", Data table → "Data table", etc.). Original domain term preserved for the brief prose so Claude sees "extracts from prospectuses" rather than "extracts from documents".

**Topic 3 — Output format**
- Interaction: structured single-select.
- Options: JSON object / Table/CSV / Markdown extraction report / Flag report / Data extraction payload / Other + free-text.
- RAG: red until picked. Green on selection.
- Mapping: → `generator.output_type`. "JSON object" and "Data extraction payload" both map to the existing "Data extraction" output option.

**Topic 4 — Target system (where the output goes)**
- Interaction: structured single-select with free-text fallback.
- Options: Simcorp / Temenos / Charles River / Bloomberg AIM / Murex / Internal spreadsheet / Downstream AI or pipeline / Advisory only — no system / Other + free-text.
- RAG: red until picked. Amber if Other + free-text is short (< 3 words). Green otherwise.
- Mapping: → new `output_destination` field on GenerateRequest. Appended to brief prose verbatim so Claude sees the specific system name.

**Topic 4b — AI platform (what runs the prompt)**
- Interaction: structured single-select. Compact pick — defaults to Claude. Can be left at default in 90% of cases.
- Options: Claude / MS Copilot — Declarative / MS Copilot — Custom Engine / OpenAI / Multi-model / Other.
- RAG: auto-green at default (Claude) on first render. User changes → stays green on any valid pick.
- Mapping: → new `ai_platform` field on GenerateRequest. The existing `deployment_target` field on prompts table stays populated with the same value for backward compat; deprecated in documentation.

**Topic 5 — Risk tier**
- Interaction: structured single-select.
- Options: Minimal / Limited / High / Prohibited (plus a one-line coaching hint per option — e.g. "High: handles personal data OR connects to critical ops process").
- RAG: red until picked. Amber if High/Prohibited picked without any of the critical-process / personal-data triggers being evident in the prose topics. Green otherwise.
- Mapping: → `generator.risk_tier`.

---

**Topic 6 — Data points to extract**
- Interaction: prose textarea + Review button.
- Coaching model: dedicated extraction-rubric variant. Claude evaluates whether each mentioned field has (a) name, (b) expected type or form, (c) rough source location. Tier-2/3-style probes per gap — e.g. "You mentioned subscription cut-off times. Should they include the time zone?" Options: "Yes as UTC offset" / "Yes as local time + TZ label" / "Source-native only" / "Split into two fields" / …
- RAG: red if < 1 field. Amber if 1-2 fields OR any field missing type/source. Green if ≥3 fields each with name + type + source.
- Mapping: concatenated into `buildBriefText()`'s prose body under a `DATA POINTS:` header.

**Topic 7 — Per-field format / normalisation**
- Interaction: prose textarea + Review button.
- Coaching model: Claude reads topic 6's field list and topic 7's format rules. Probes missing per-field specifics. "You said 'amounts'. Should the prompt output amounts as strings with currency symbol or as float + currency field?"
- RAG: red if no formats given and topic 6 is non-empty. Amber if some fields specified, not all. Green if each named field has a format rule OR explicit "output as-is, no normalisation".
- Mapping: concatenated under `FIELD FORMATS:`.
- Cross-topic dep: requires topic 6 answered; Claude has access to topic 6 via sibling context.

**Topic 8 — Null / missing handling**
- Interaction: prose textarea OR structured pick. Offer both: four preset options ("null with confidence: low" / "explicit 'not-found' string" / "skip the record" / "raise error") plus free-text for more nuanced policies.
- RAG: red until answered. Green on any explicit policy (preset or prose).
- Mapping: concatenated under `NULL HANDLING:`.

**Topic 9 — Confidence and traceability**
- Interaction: structured single-select with coaching follow-up.
- Primary options: "Yes — confidence + page/section ref per field" / "Yes — confidence only" / "Yes — page refs only" / "No — values only".
- Follow-up coaching if "Yes — page refs…" picked: Claude probes "Page refs to what granularity? Page number, section title, paragraph?" options in tier-3 style.
- RAG: red until answered. Amber if "Yes — page refs…" picked without granularity. Green otherwise.
- Mapping: concatenated under `TRACEABILITY:`. Also feeds into guardrail auto-selection (REG_D4 Audit Trail).

**Topic 10 — Error / exception modes**
- Interaction: prose textarea + Review.
- Coaching model: probe for at least one handled error mode. "What if the prospectus is missing the section you need?" options.
- RAG: red if empty. Amber if one mode stated. Green if ≥2 modes OR explicit "out of scope, fail loudly" policy.
- Mapping: concatenated under `ERROR MODES:`.

### B3. UI sketch

Single-screen checklist replacing the current Step 1-4 progression. (Steps 5 Constraints and 6 Guardrails remain as subsequent stages — see B6 #7.)

```
┌─────────────────────────────────────────────────────────────────┐
│ Brief Builder — Step 1: Build your brief                        │
│                                                                  │
│  4 complete   3 in progress   4 to start         [Next stage]   │
│  ●●●●──────────────────────────                   (active when  │
│                                                    ≥1 topic ●)  │
│                                                                  │
│  ① Prompt Type                 ●green   Extraction              │
│  ② Source document type        ●green   Prospectus              │
│  ③ Output format               ●amber   JSON object (see note)  │
│  ④ Target system               ●green   Simcorp Dimension       │
│  ④b AI platform                ●green   Claude (default)        │
│  ⑤ Risk tier                   ●amber   Limited (see note)      │
│  ─────────                                                      │
│  ⑥ Data points to extract      ●red    Click to answer          │
│  ⑦ Per-field format            ●red    Click to answer          │
│  ⑧ Null / missing handling     ●amber  "return null"            │
│  ⑨ Confidence and traceability ●green  Yes — page refs, section │
│  ⑩ Error / exception modes     ●red    Click to answer          │
└─────────────────────────────────────────────────────────────────┘
```

**Cold start UX:**

On first render with zero topics answered, the page shows a small prominent callout above the topic grid:

```
  ┌─────────────────────────────────────────┐
  │  Start here — your answer determines    │
  │  the rest.                              │
  │                                         │
  │  [  Pick Prompt Type  →  ]              │
  └─────────────────────────────────────────┘
```

Click scrolls to and expands Topic 1. Once Topic 1 is green, the callout is replaced by the normal progress indicator. If the user tries to expand a later topic without Topic 1 set, a one-time hint appears: "Pick Prompt Type first — the rest of the checklist depends on it."

**Structured topic collapse behaviour:**

Picking an option in any structured topic auto-collapses the row and displays the picked value in the row summary ("Extraction", "Prospectus", etc.). The row remains clickable — user can re-expand to change. Re-expand shows the current pick highlighted; picking a different option re-collapses with the new value. No separate Save button for structured topics; pick IS save.

Prose topics do not auto-collapse on save — user explicitly collapses via a ✕ in the card header, or expanding another topic (which collapses the current one). Prose topics retain the "Review" and "Re-review" buttons defined in the existing Step 1 refinement loop.

**Interactions:**
- Each topic is a clickable row. Click expands the topic in-place. Only one topic expanded at a time.
- Structured topics expanded: option buttons + (if applicable) free-text input. Picking an option collapses the row.
- Prose topics expanded: textarea + Review button. Review triggers the per-topic validate call. Claude's probe (amber/red feedback) renders inline below the textarea with "Use this suggestion" / "Ignore this line of thought" buttons — same UX vocabulary as today's Step 1 refinement loop, just scoped to one topic.
- Topic order on screen is fixed (logical: metadata first, prose second). User picks any topic to tackle.
- "Next stage" button: top-right, enabled once at least one topic is green. No forced gating on all-green.
- "Checking…" indicator near the Review button during a topic-level validate.
- Optional: a compact "Restructure brief" button at the bottom, available when ≥ 50% of topics are green — triggers the existing `/prompts/briefs/restructure` path.

**Abandon / resume behaviour:**

All topic state lives in `Brief.step_answers` (JSON TEXT column, already in the schema). Each user action (structured pick, Review-passed prose, dismiss) triggers a PATCH to `/briefs/{id}` persisting the updated `step_answers` JSON. Abandoning the tab and returning — same browser or different device — rehydrates the checklist from `Brief.step_answers` on `viewInits.brief`. No localStorage dependency; server is authoritative.

**Prompt Type change UX — preview before confirm:**

If the user re-expands Topic 1 after other topics are answered and picks a different Prompt Type, a confirmation modal appears with two columns side by side:

```
  Switching to Classification — preview

  ┌─── These stay ─────────┬─── These reset ────────────┐
  │ ④ Target system        │ ⑥ Data points to extract   │
  │    (Simcorp)           │    (your text cleared)     │
  │ ④b AI platform         │ ⑦ Per-field format         │
  │    (Claude)            │ ⑧ Null / missing handling  │
  │ ⑤ Risk tier            │ ⑨ Confidence/traceability  │
  │    (Limited)           │ ⑩ Error / exception modes  │
  │                        │    (all cleared)           │
  └────────────────────────┴────────────────────────────┘

  [  Confirm switch  ]      [  Cancel, keep Extraction  ]
```

The "These stay" column lists topics whose answers are valid across prompt types (target system, AI platform, risk tier). The "These reset" column lists prompt-type-specific prose topics whose content would not make sense under a different type.

Structured topics 2 and 3 (Source document type, Output format) reset on prompt-type switch because their options/defaults shift per type — but the currently-picked value is preserved if it exists in the new type's option list. Shown in the "These stay (if option available)" row.

### B4. Data model changes

**`Brief.step_answers` (existing JSON TEXT column):** structure changes from the current flat `{purpose, inputType, …}` to per-topic:

```json
{
  "topic_1_prompt_type": { "value": "Extraction", "state": "green", "updated_at": "…" },
  "topic_2_source_doc":  { "value": "Prospectus", "state": "green", "updated_at": "…" },
  "topic_4b_ai_platform":{ "value": "Claude", "state": "green", "updated_at": "…" },
  "topic_6_data_points": {
    "value": "subscription cut-off time (HH:MM + TZ)…",
    "state": "amber",
    "conversation_history": [ { "question": "…", "answer": "…", "skipped": false } ],
    "updated_at": "…"
  }
}
```

No DB schema change required (still a TEXT column storing JSON). Pydantic schemas for Brief IO will need a structured model for the per-topic shape.

**`ConversationEntry`:** gains `topic_id: str | None = None`. Backend filter continues to forward real Q&A, now scoped per topic when the validate call is topic-level.

**Generator schema (revised — splits deployment_target):**

`GenerateRequest` gains two new fields:

```python
class GenerateRequest(BaseModel):
    # existing fields...
    ai_platform: str = "Claude"          # NEW — what runs the prompt
    output_destination: str | None = None # NEW — where the output goes (free-form or enum-constrained)
    deployment_target: str = ""           # DEPRECATED — kept for backward compat; populated with ai_platform value
```

The prompts table schema: add `ai_platform` column and `output_destination` column (nullable). `deployment_target` column stays populated with the same value as `ai_platform` for now; a later migration can drop it once all call sites are updated.

**New endpoint `POST /prompts/briefs/validate-topic`:** request shape:

```json
{
  "topic_id": "topic_6_data_points",
  "prompt_type": "Extraction",
  "topic_answer": "subscription cut-off time (HH:MM + TZ), ISIN, minimum investment…",
  "sibling_answers": { "topic_2_source_doc": "Prospectus", "topic_3_output": "JSON object", "…": "…" },
  "conversation_history": [ "…entries with topic_id == topic_6 only…" ]
}
```

Response shape:

```json
{
  "state": "amber",
  "suggestion": "…",
  "suggested_addition": "…",
  "question": "…",
  "options": [ "…6 items…" ],
  "free_text_placeholder": "…"
}
```

Any or all of `suggestion`, `question`, `options`, `free_text_placeholder` may be null depending on state and probe style.

The existing `/validate-brief` stays for backward compat. Retires once the checklist UI ships and the old prose-only Step 1 is removed.

**Anti-drift rule in validate-topic system prompt:**

Explicit, strongly phrased rule — to be prototyped against Claude before build and confirmed in a small test:

> You are reviewing ONLY the focal topic. Sibling answers are provided for context — you may reference them to understand the brief's shape, but you MUST NOT probe gaps in sibling topics. If a gap exists in a sibling topic, silently ignore it. The user will address sibling topics separately.

Phrasing may need iteration. Recommend a pre-build dry-run: 5-10 test briefs with deliberate sibling-topic gaps, observe whether Claude stays focused on the focal topic or drifts into probing siblings. If it drifts, experiment with variants ("refuse to probe", "answer only about the focal topic", role boundaries). Do not ship until drift rate is acceptable (< 10% of calls drift).

**Generator call:** `/prompts/generate` picks up the structured topic values directly. `prompt_type`, `input_type`, `output_type` from topics 1, 2, 3. `ai_platform` from topic 4b. `output_destination` from topic 4. `risk_tier` from topic 5. `brief_text` composed from prose topics 6-10 with labelled headers.

**Brief → Prompt handoff:** `_briefSend` now has authoritative values for all five structured fields (no `typeMap` inference). Generator screen pre-fill becomes a straight copy. `typeMap` can be deleted.

### B5. Cost and latency considerations — Haiku for per-topic validation

**Problem:** A per-topic validate fires one Claude call per user Review click. With 10 topics × 3-5 reviews each = 30-50 Claude calls per brief. At Sonnet prices and latency this is non-trivial.

**Proposal:** Evaluate Haiku for per-topic validation before build.

**Test protocol:**
1. Pick 5 representative Extraction briefs at various completion states (some red topics, some amber, some green).
2. Run each topic's `validate-topic` twice: once with Sonnet, once with Haiku, using the same system prompt and the same sibling context.
3. Compare: (a) RAG classification agreement rate between Sonnet and Haiku, (b) suggestion quality (human review — is the suggestion specific to the brief or generic?), (c) question quality (does Haiku generate grounded questions or fall back to prompt-engineering platitudes?), (d) latency per call.
4. Decision rule: if Haiku agrees on RAG state ≥ 90% of the time AND suggestion/question quality is "usable" (human review says yes), ship Haiku for per-topic validation. Keep Sonnet for whole-brief restructure (runs once per brief, quality matters more).

**Cost estimate at Haiku pricing:** per-topic validation drops from ~$0.30 per brief (Sonnet) to ~$0.02 per brief. Meaningful at scale.

**Add as design consideration, test before first build session commits to a model.**

### B6. Open questions and judgement calls

1. **Source document type ↔ Input Type mapping.** Topic 2 uses domain terms (Prospectus, Policy). Generator's `input_type` uses technical categories (Document or report, Data table). Proposal: keep both; store the domain term on the brief, translate to the enum for the generator. The domain term is preserved in brief prose so Claude sees it. **Needs confirmation.**

2. **~~Target system ↔ Deployment Target mismatch.~~** **Resolved per review** — split into `ai_platform` (topic 4b) and `output_destination` (topic 4). Generator schema gains two new fields; `deployment_target` deprecated but retained for backward compat. See Part B4.

3. **RAG transitions — Claude-driven or user-override?** Default to Claude-driven via `validate-topic`. Add a "Mark complete" button on each prose topic so the user can override to green. Useful when Claude is pedantic and the user knows the answer is sufficient.

4. **~~Multi-topic shared context for validate-topic.~~** **Resolved per review** — sibling answers included on every request; anti-drift rule in system prompt is explicit and pre-build-tested. See Part B4.

5. **Prompt-type-specific topic lists.** This session designs Extraction only. Each of the other seven prompt types gets its own list in later sessions. Topic 1 (Prompt Type) is shared; once the user picks, the checklist for the chosen type renders. If user changes Prompt Type mid-build, preview modal shows what stays vs resets before confirming (see B3). **Resolved per review.**

6. **Migration of existing in-progress briefs.** Current briefs have `state.purpose` + step_progress. Proposal: one-time migration when a user resumes — synthesise a single topic "topic_legacy_purpose" holding the old purpose text in amber state; show the user a "This brief predates the new checklist — we've carried your purpose across. Review and split into topics." banner. Fresh briefs start clean.

7. **Constraints and Guardrail selection (current Steps 5-6) — topics or separate stages?** Proposal: keep as separate stages after the topic checklist. They operate on the brief as a whole, not per-domain-concern. Alternatively Constraints could become a multi-select topic, but Guardrails need their own stage because they drive compliance scoring.

8. **"Not applicable" per topic.** Some topics are genuinely optional (e.g. topic 10 Error modes for a simple one-off extraction). Proposal: each topic gets a "Not applicable" pill that collapses it to grey (excluded from counts). User must confirm N/A once.

9. **Default screen order.** Topics 1-5 first (structured, fast wins), 6-10 after (prose, domain-specific). Red topics visually higher priority via colour only, not reordering — fixed order aids muscle memory on return visits.

10. **When does a prompt_type switch re-scope the topic list?** Preview modal before confirm (see B3). Structured topics 4, 4b, 5 preserved; prose topics 6-10 reset.

11. **~~Per-topic validate cost.~~** **Resolved per review** — Haiku evaluation before build. See Part B5.

12. **Coaching output when ALL topics green.** Does the user get a summary card? A single "proceed" CTA? Proposal: a summary card appears at the top: "Brief is complete. Click Next stage when you're ready." Next stage was always available; no behavioural change, just affirming feedback. No auto-advance.

13. **Per-topic `validate-topic` — one shared system prompt or per-topic prompts?** Proposal: one shared system prompt with a `=== TOPIC ===` section that swaps in the rubric for the current `topic_id`. Keeps the prompt-engineering surface single-file.

### B7. Judgement defaults applied unless overridden

- Topic 1 = Prompt Type as the first row, determines which list renders. Only Extraction specced this session.
- Split `deployment_target` into `ai_platform` + `output_destination` at the generator schema level.
- Topic 4 = business system (output_destination); Topic 4b = AI platform (ai_platform, defaults Claude).
- Claude-driven RAG with user override via a per-topic "Mark complete" button.
- Sibling context passed on every `validate-topic` request; anti-drift rule enforced in system prompt.
- Type-switch shows preview, preserves structured picks where valid, resets prose.
- One-time migration banner for in-progress legacy briefs.
- Constraints + Guardrail selection stay as separate stages after the checklist.
- "Not applicable" available on every topic.
- Fixed row order (structured 1-5 plus 4b, prose 6-10).
- Single shared system prompt with topic_id switch for all topic-level coaching.
- Haiku evaluated before build for per-topic validation; decision deferred to test result.

---

## Revision log

- **Initial design:** produced in reconnaissance session following 19 April smoke test findings.
- **Revision 1 (this doc):** split `deployment_target` into `ai_platform` + `output_destination`; added Topic 4b; added explicit anti-drift rule with pre-build test protocol; added Haiku cost/latency evaluation protocol; added cold-start UX callout; added structured-topic auto-collapse behaviour; named abandon/resume persistence mechanism explicitly; replaced Prompt Type change warning with side-by-side preview modal.
