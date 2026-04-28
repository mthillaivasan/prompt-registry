# Library Drop L2 — Complete

Date: 2026-04-28 · Branch: `run-a` · Spec: PHASE2.md "Brief Builder example
library — Drop L2" + PHASE3.md "Brief Builder design principle (logged
27 April 2026)".

---

## What landed

| Component | Where | Status |
|---|---|---|
| Matching service | `services/library_matching.py` + `seed/library_matching.yml` | New |
| Schema — approved refs on brief | `app/models.py` `Brief.approved_library_refs`, `migrations/001_initial.sql`, `app/migrations.py` runtime ALTER | New |
| Endpoints — matches + references | `app/routers/briefs.py` `GET /briefs/{id}/library-matches` and `GET /briefs/{id}/library-references` | New |
| Approval persistence | `BriefUpdate.approved_library_refs` + PATCH wiring on `update_brief` and `save_step` | New |
| validate-topic feed | `static/views/brief.js` `_callValidateTopic` fetches approved excerpts when not cached | Wired through existing `reference_examples` field on `ValidateTopicRequest` (added in L1 follow-up) |
| Generator feed | `app/schemas.py` `StructuralReference` + `GenerateRequest.reference_examples`, `app/routers/generation.py` user-message append | New |
| Brief Builder UI | `static/views/brief.js` matches panel + Approve/Remove buttons + `_loadLibraryMatches` | New |
| Generator UI handoff | `static/views/generator.js` forwards `window._briefReferenceExamples` on `/prompts/generate` | New |
| Tests | `tests/test_library_matching.py` (10) + `tests/test_brief_library_l2.py` (15) | +25 |

---

## Matching approach chosen — and why

**Deterministic tag overlap, no embeddings.**

The library is small at L1/L2 scale (low tens of entries, low hundreds at the
horizon I can see) and the matching signal is already curated on every row:
`prompt_type` (required), `domain` (`finance` / `general`), and a hand- or
Haiku-tagged `topic_coverage` JSON array. Ranking by overlap on those tags
answers the load-bearing question — "users building similar briefs made
these choices" — directly and auditably.

A semantic / embedding-based match would have added real cost with no lift
at this scale: an ANN index (pgvector or a separate service), an embedding
pipeline triggered on every library mutation, and ranker non-determinism
that would complicate testing. The deterministic path also keeps the
configuration-first discipline intact — weights live in
`seed/library_matching.yml`, not in code.

The score formula:

```
score = topic_coverage_weight × |requested_topics ∩ entry.topic_coverage|
        + (domain_match_weight if entry.domain == requested.domain else 0)
```

Configured weights: `topic_coverage_weight = 2.0`, `domain_match_weight = 1.0`.
Topic overlap of one match outweighs domain match alone — a cross-domain
example with strong tag overlap ranks above a same-domain example with no
overlap. That's the right priority order: topic relevance is the harder
signal to substitute for.

Sort: score desc, ties broken by `created_at` desc (newest first).

**Revisit when:** the library exceeds ~500 entries, or users routinely
approve matches whose topic coverage diverges from the brief's signalled
topics (i.e. tag overlap stops correlating with user approval). Both
signals would tell us tags are no longer doing the work.

---

## UI pattern chosen — and why

**Inline panel between the brief textarea and the prose-topic cards on
Step 2.**

Three options were on the table:

1. **Sidebar panel.** Rejected: would compete for attention with the
   prose-topic cards already living to the right of the textarea on
   wider viewports, and the sidebar wouldn't appear at all on narrow
   viewports.
2. **A separate "review references" step.** Rejected: forces a
   gear-change in the speed-to-v1 flow. PHASE3.md is explicit — the
   library should not interrogate the user before a v1 exists. A
   dedicated step reads as required when it isn't.
3. **Inline reference list.** Chosen. Sits in the same column as the
   brief and the topic cards, so users can scan it while writing the
   brief — which is exactly when the examples are useful. Empty state
   (no matches found) collapses to nothing rendered, keeping the v1
   flow clean for users in domains the library doesn't yet cover.

Each match card shows title, source provenance, summary, and a single
**Approve as reference** button (toggling to `✓ Approved` + a paired
**Remove** button when the user clicks). Approval persists immediately
via PATCH `/briefs/{id}` with optimistic local state and revert-on-error.

The L2 spec asked us to surface candidates "at the appropriate step" —
Step 2 is the right slot because that's where the user is composing the
brief prose and where coaching happens. Showing them earlier (Step 1
metadata pick) would be too late to ground writing; showing them later
(Step 3+ audience/constraints/guardrails) is past the point where prose
shape can be informed.

The "See reference" button on each prose-topic card now reads from the
**approved-only** set rather than `/library/relevant`. Unapproved matches
never reach coaching — even if they would have surfaced in the L1
relevance feed.

---

## Where approval state lives

`briefs.approved_library_refs` — `TEXT NOT NULL DEFAULT '[]'`, JSON array
of `library_id`s.

- **Persisted via** the existing PATCH `/briefs/{id}` and PATCH
  `/briefs/{id}/step/{n}` endpoints (`BriefUpdate.approved_library_refs`).
  Reusing the existing PATCH avoids a bespoke approve/reject endpoint —
  the array is the source of truth, the client sends the full intended
  state.
- **Read by** the new `GET /briefs/{id}/library-matches` (joins against
  approval state to set the `approved` flag per match) and `GET
  /briefs/{id}/library-references` (returns approved entries only).
- **Surfaced on** `BriefOut.approved_library_refs` (parsed list[str] via a
  field validator, mirroring the `topic_coverage` pattern from L1).

Migration: `app/migrations.py` adds the column at startup for SQLite
(runtime PRAGMA-guarded ALTER) and Postgres (idempotent ALTER ADD COLUMN
IF NOT EXISTS). Authoritative SQL in `migrations/001_initial.sql` updated
to match for fresh databases.

---

## Test count delta

- Before L2: 267 passing
- After L2: **292 passing** (+25)
- New test files:
  - `tests/test_library_matching.py` — 10 tests covering deterministic
    ranking, configured limits, score values.
  - `tests/test_brief_library_l2.py` — 15 tests covering the new endpoints,
    approval persistence round-trip, and the generator structural-reference
    block.
- No existing tests modified or removed. `test_validate_topic.py` already
  asserted the `reference_examples` injection path (added in L1
  follow-up); L2 just changes which entries the frontend sends.

---

## Decisions that could have gone differently

### Domain derivation

The L2 spec says "given a brief (description + chosen prompt_type +
chosen domain)". I deliberately avoided introducing a new "pick a
domain" step in the Brief Builder — that would have violated the
speed-to-v1 principle and added one more thing for users to fill in
before any code runs.

Instead, **domain is derived**: `finance` if the brief carries a
`client_name`, else `None` (no domain bonus applied). The registry's
audience is regulated finance, and a populated client_name is a strong
signal of a finance use case. A null client_name leaves matching
domain-agnostic — both `finance` and `general` library entries compete
purely on topic overlap.

**Could have done instead:** asked the user explicitly. Rejected for
flow-cost reasons. If the heuristic proves wrong (e.g. internal-IT briefs
always carry a client_name and shouldn't favour finance), revisit.

### Topic-coverage signal

The brief's "topic signal" — the topics fed into matching as the request
side of the overlap score — is derived from `step_answers`: every topic
whose state is `amber` or `green` (i.e. the user has thought about it).
Red and missing topics don't contribute.

**Could have done instead:** use only green topics, or only the topics
the user has typed prose against. The amber-or-green choice keeps the
signal more inclusive — even a partial answer about, say, null handling
counts as "this brief is thinking about null handling, surface entries
that have done so too." If matches feel too noisy in practice, tighten
to green-only.

### Approval endpoint shape

Two approaches considered:

1. **Bespoke endpoint** — `POST /briefs/{id}/library-approvals` with
   `{library_id, approved}`, server-side toggling.
2. **Reuse PATCH** — extend `BriefUpdate.approved_library_refs` and let
   the client send the desired full state.

Chose option 2. The brief is already a heavily-PATCH'd resource (every
step writes through the same handler), and approval is conceptually a
field on the brief, not a separate sub-resource. Optimistic UI state +
PATCH-on-toggle keeps the wire chatter small. The trade-off: the client
must hold the full intended approved set, but it does anyway because the
matches panel renders from local state.

### Conditional questioning by output structure

PHASE3.md was explicit that conditional questioning by output structure
(JSON / structured / unstructured) is iteration work, not v1 work. I did
not implement it. PHASE3.md continues to carry it as a deferred item —
no action needed there.

### Single-step matching vs continuous matching

Matches load once when the user enters Step 2 (or resumes a brief at
Step 2). They do not re-fetch when the user toggles topic state, edits
prose, or otherwise updates the brief on Step 2. Rationale: at this
library scale the top-3 set will rarely flip on small edits, and a
shifting sidebar is more annoying than helpful. If this proves wrong as
the library grows, re-trigger on `topic_*` state changes.

---

## What's deferred

Logged to PHASE3.md or already there:

- **Conditional questioning by output structure** (JSON / structured /
  unstructured) — already in PHASE3.md, untouched.
- **Continuous matching** — re-rank on every state change. Not needed at
  current scale.
- **Cross-prompt-type matches** — matching today is hard-filtered by
  prompt_type. An Extraction example can't surface for a Classification
  brief even if topic overlap is high. Probably right at this stage; if
  cross-type insight becomes valuable, relax the filter and use prompt_type
  as a soft ranking signal instead.
- **Server-side semantic indexing** — pgvector + an embedding pipeline.
  Not needed at current scale; flagged in the matching service's
  module docstring with the revisit criteria.
- **Curator workflow for "promote a generated prompt into the library"** —
  carried over from L1, still deferred.
- **Match against finalised registry prompts, not just library entries** —
  the "Learning layer from completed prompts" PHASE2 section is still
  separate from the seeded library; merging the two surface areas is a
  later cut.

Added to PHASE3.md by this drop:

- *(none)* — the items above were already on file.

---

## Hard rules honoured

- **Stayed on `run-a`.** No commits or pushes touching `main`.
- **Tests stayed green throughout.** Every commit ran the relevant subset
  before push (full suite verified at the end).
- **Commit per logical unit.** Six commits: matching service, approval
  schema, UI + endpoints, validate-topic wiring, generator wiring, tests.
- **Configuration-first.** Weights, default top-N, and the min-score
  floor live in `seed/library_matching.yml`, not in code.
- **No conditional output-structure questioning.** v1 stays minimal;
  iteration depth is deferred.
- **User approval gates downstream.** validate-topic and the generator
  consume only entries on `briefs.approved_library_refs`. Empty approval
  → empty downstream feed.

*End of L2 sign-off.*
