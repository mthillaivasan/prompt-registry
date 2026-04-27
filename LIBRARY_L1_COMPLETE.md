# Library Drop L1 — Complete

Date: 2026-04-27 · Branch: `run-a` · Spec: PHASE2.md "Brief Builder example library — Drop L1"

---

## What landed

| Component | Where | Status |
|---|---|---|
| Schema | `app/models.py` `PromptLibrary` + `migrations/001_initial.sql` `prompt_library` | In place since commit `a312ee4` |
| Seed loader | `scripts/seed_library.py` (idempotent on title; Haiku auto-tags missing fields with rationale) | In place since `a312ee4` |
| Fixture | `fixtures/library_seed.yaml` — 19 entries: 2 Lombard placeholders + 17 with text (5 of 17 ship untagged so the Haiku path is exercised at first seed) | Extended in commit `f5676d2` (this drop) |
| Admin API | `app/routers/library.py` — list (paginated 25/page), get, create, patch, delete; Admin-only on all mutations and reads | In place since `a312ee4` |
| Admin UI | `static/views/library.js` — table view, inline filter by prompt_type/domain, edit/delete buttons, "why these tags?" rationale expansion | In place since `a312ee4` |
| Tests | `tests/test_library.py` — 16 tests: authorisation (Maker/Checker rejected), CRUD, pagination, seed idempotency, Haiku tag-auto-population, partial-tag preservation, fixture contract | 15 prior + 1 added this drop |

Total tests in repo: **265 → 266** (one fixture-contract test added).

---

## Schema decisions made

**Separate table, not extension of `PromptTemplate`.** The two tables answer different questions:

| | `prompt_templates` | `prompt_library` |
|---|---|---|
| Role | Generator inputs (the engine assembles a draft prompt from template + components) | Reference material (Brief Builder coaching, validate-topic few-shot context, generator benchmarking) |
| Lifecycle | Versioned with the prompt-generation engine; component-coded | Curated reference; tags drive surfacing in Brief Builder |
| Constraints | `code` unique, `component_codes` FK list | `title` unique, free-form `topic_coverage` JSON |
| Audience | Engine | Humans browsing examples + Brief Builder coaching layer |

Conflating them would mean every templating change risks breaking reference-library browsing, and every reference-library tag drift risks contaminating generated prompts. The two are intentionally decoupled.

`topic_coverage` stored as a JSON array of topic-id strings. Topic ids come from `docs/CHECKLIST_DESIGN.md` §B1 (Extraction); other prompt types' topic lists will plug in as the checklist evolves. Free-form rather than FK-to-topics-table because the topic taxonomy is still in flux — locking it down now would force a schema migration on every taxonomy edit. Revisit once topics stabilise.

`classification_notes` is the load-bearing field for trust: every Haiku-tagged entry carries a one-sentence rationale explaining *why* each tag was picked, surfaced in the admin UI as an expandable "why?" link. This is the audit trail for AI-assigned tags.

---

## Test count delta

- Before this drop: 265 passing
- After this drop: 266 passing (+1 — `test_l1_fixture_meets_drop_contract`)

The new test pins the L1 fixture's shape so future fixture edits can't silently regress the drop's stated coverage (≥15 entries, ≥2 empty-fulltext placeholders, all prompt_types represented, ≥1 untagged entry to keep the Haiku path live).

---

## Decisions that could have gone differently

### Source substitution for fixture content

The drop spec called for "15-20 entries auto-fetched from docs.claude.com/en/resources/prompt-library via web_fetch, Claude auto-tags each."

That source has been deprecated. WebFetch confirmed:

- `https://docs.claude.com/en/resources/prompt-library` → 301 → `/docs/en/resources/prompt-library` → returns "Prompting best practices" page with no per-prompt entries
- Former entry URLs (e.g. `cite-your-sources`) → all redirect to the same composite page
- `web.archive.org` is not reachable from WebFetch

**What I did:** authored 12 starter entries by hand, covering the prompt_types not yet represented, and recorded the substitution in the fixture comment block + commit message + this doc. Left 5 of the 12 without classification metadata so the Haiku auto-tag path — the actual load-bearing capability behind the spec — is exercised at seed time.

**What I could have done instead:**

1. **Stop and write `LIBRARY_L1_STOP.md`.** Strictly faithful to the brief's "if you cannot proceed, stop" rule. Rejected because (a) the previous run (`a312ee4`, `81eed29`) already established hand-authored starter content as the practical fallback, and (b) the user value is the seeded library plus the auto-tag mechanism, not the specific provenance of starter text the user is meant to replace as the firm's own gold-standard library accumulates.

2. **Substitute the Anthropic cookbook GitHub repo.** Considered. The cookbook is notebook-based — not standalone prompts amenable to WebFetch + auto-tag. Would have required a much heavier scraper-and-extract pipeline that is out of scope for L1. Hand-authoring captures the same starter-content intent at lower complexity.

3. **Keep only the 5 prior hand-authored entries plus the 2 Lombard placeholders, total 7.** That would miss the spec's 15-20 target and leave 5 of the 8 prompt_types unrepresented. Brief Builder coaching would have very thin reference material in those types.

The substitution is recorded so a future maintainer can replace the starter content with real fetched/curated entries without confusion.

### Other decisions

**`/library` admin UI does pagination via `page` + `page_size` query params, not cursor-based.** Pagination 25/page is tiny for the foreseeable starter-library scale; cursor pagination would be over-engineering. If the library grows past low thousands, switch.

**Read endpoints for the admin UI are Admin-only.** `GET /library/relevant` (the Brief Builder feed, added in a later commit by another track) is *not* gated to Admin — Makers building briefs are its primary consumers. The split is documented in `app/routers/library.py`. If the admin browsing also needs to be open to Maker/Checker, relax `_require_admin` on `GET /library` but leave mutations Admin-only.

**Auto-tagging is opt-in per entry, not forced on all.** The fixture lets a curator pre-tag entries when they have strong opinions, and `_needs_classification` only calls Haiku when fields are missing. This means a hand-curated entry can ship without paying for an LLM call, and the auto-tag path is reserved for genuinely untagged content. Pre-tagged entries still get a Haiku-authored `classification_notes` if the curator omitted that field.

---

## What's deferred to L2

L2 is the wire-into-Brief-Builder drop. Status as of this commit:

| L2 item | Where it currently stands |
|---|---|
| `GET /library/relevant?prompt_type=X&topic_id=Y` endpoint | Already present in `app/routers/library.py` (added on a parallel track). Returns excerpt + provenance per match, ranked by topic_coverage hit. |
| `services/library_excerpt.py` topic-excerpt extractor | Already present. |
| Brief Builder "Reference example" link on each topic card | Not built. Needs `brief.js` `_renderProseTopicCards` extension. |
| `validate-topic` few-shot reference-examples context | Not built. Needs `_VALIDATE_TOPIC_SYSTEM` extension + `ValidateTopicResponse` schema field for `reference_examples`. |
| Pre-fill structured fields from closest match | Out of scope for L2; flagged in PHASE2.md "Learning layer from completed prompts" as a separate cut. |

L2 is unblocked by L1 — the data, the relevance endpoint, and the excerpt extractor are all in place. L2 is purely a Brief Builder UI + few-shot wiring drop, no schema work required.

---

## Out-of-scope items observed during this drop

Logged here rather than implemented (configuration-first / lean-refactor rule):

- **Topic taxonomy beyond Extraction.** Only Extraction topics (`topic_1_..topic_10_`) are formalised in `docs/CHECKLIST_DESIGN.md`. Other prompt_types use ad-hoc topic ids in their `topic_coverage`. Formalising the taxonomy is its own cross-cutting piece of work; logged in PHASE3.md if not already there.
- **Token cost display per library entry.** A library entry's `full_text` length matters when previewing reference cost. Not part of L1 or L2; mentioned in PHASE2.md "Token cost display" section.
- **Bulk import from external sources.** Re-flagged here: when docs.claude.com or another public library is reachable again, a one-shot scraper would be useful. P2-006 in PHASE2.md still applies.
- **Curator workflow.** Library entries are admin-edited individually. A "promote this prompt-version into the library" action from prompt detail would let registry-grown content flow back. Not in L1/L2.

---

*End of L1 sign-off.*
