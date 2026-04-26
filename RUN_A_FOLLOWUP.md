# Run A — follow-up

Two small items actioned on `run-a` after the forensics review of the
26 April 09:50 UTC prompt. One commit per item, no merge to `main`.

## Item 1 — REG_D2 split

**What changed.** `_REG_D2_INSTRUCTIONAL_TEXT` in `app/seed.py` was the
AUDIT-section scaffold telling the LLM to emit a trailing AUDIT block
populated by runtime variables. That is wrapper-metadata-shaped
(structure rendered around output) rather than runtime instruction.
Rewrote the constant to the AI-generated / advisory disclosure portion
only — the genuine prompt_content half of the dimension. The empty
AUDIT trailer no longer appears in generated prompts.

**Files.** `app/seed.py` (constant body), `tests/test_generation.py`
(two assertions that previously locked in `"AUDIT" in sent_system`
swapped to assert the new disclosure marker is present and AUDIT is
absent).

**`_CONTENT_TYPES_BY_CODE`.** No change — REG_D2 stays
`prompt_content`. The "split" is between the dimension's two pieces
of content; only the disclosure half remains as injected text. The
classification map's value for REG_D2 is still correct after the
change.

**Decision — where the AUDIT scaffold went.** Removed entirely from
seed-time content. It was never a runtime LLM instruction; it was UI
scaffolding masquerading as one. The audit-trail concept lives in
REG_D4 (Audit Trail), which is already classified `wrapper_metadata`
and is now surfaced by the new Governance Context panel (Item 2). No
new dimension code, no schema change.

**Commit.** `da97cfe` — Item 1 — REG_D2 split: drop AUDIT scaffold
from prompt body.

## Item 2 — Governance Context panel

**What changed.** New read-only panel on the prompt detail page that
surfaces the five `wrapper_metadata` dimensions (REG_D1 Human
Oversight, REG_D4 Audit Trail, REG_D5 Operational Resilience,
NIST_GOVERN_1 Governance Accountability, NIST_MAP_1 Context and
Limitations) alongside the prompt body. Reviewers and auditors can
consult these as governance context that applies to the prompt
without expecting them inside the prompt body.

**Files.** `app/routers/compliance.py` (new endpoint `GET
/scoring-dimensions/wrapper-metadata`), `static/views/detail.js`
(panel render + fetch), `tests/test_compliance.py` (positive +
negative coverage on the endpoint).

**Endpoint shape.** `{code, name, framework, source_reference,
description, score_5_criteria}` per row. Filtered server-side to
`is_active=True AND content_type='wrapper_metadata'`. Returns the
five expected codes; excludes `prompt_content` and `registry_policy`
classifications.

**Decision — Phase 1 cut, catalogue-level only.** PHASE2.md line 351
envisions per-prompt fields on the panel (named accountable reviewer,
audit-trail format, manual-fallback description, in/out-of-scope use
cases). That requires schema additions and write paths and is a
larger piece of work. The Phase 1 scope here is read-only surfacing
of the dimension catalogue so the user-facing concept exists; the
per-prompt assignment work is a follow-on.

**Commit.** `3e85b7b` — Item 2 — Governance Context panel on prompt
detail.

## Test posture

Full suite green at both commits — 264 passing after Item 1, 265
after Item 2 (one new test on the endpoint). Existing
`test_generation.py` assertions on `"AUDIT" in sent_system` were
updated rather than deleted: they now lock in the new disclosure text
and explicitly assert the AUDIT scaffold is absent.

## Out of scope

- Per-prompt wrapper-metadata fields (PHASE2 §351 fields list).
- Registry-policy enforcement machinery (PHASE2 §352, separate arc).
- Migrating the generator from the legacy 17-row `scoring_dimensions`
  catalogue to the new 23-row `dimensions` catalogue.
- Removing `REGULATORY_COMPONENTS` static dict from
  `services/prompt_components.py` (per PHASE2 "Dimension migration
  pattern" — the dual-source-of-truth question is unchanged).
