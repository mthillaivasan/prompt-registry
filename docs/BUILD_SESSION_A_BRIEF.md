# Build Session A — Topic Model and `validate-topic` Endpoint

**Scope marker:** Phase A of the topic-checklist build. Infrastructure only. No UI this session; no integration with the generator; no prose-topic coaching logic beyond the rubric scaffold.

**Companion doc:** `docs/CHECKLIST_DESIGN.md` — full design. Read before starting.

---

## Scope — what this session builds

1. **Topic model on `Brief.step_answers`** — a structured per-topic JSON shape replacing the current flat `{purpose, inputType, outputType, audience, …}` blob. Backward-compatible migration path for in-progress briefs.

2. **State machine for each topic** — red / amber / green transitions, persisted in `step_answers`. Structured topics: pick-to-green. Prose topics: state set by `validate-topic` response. "Mark complete" override stored on the topic record.

3. **Topic-to-validation mapping** — a server-side registry mapping `topic_id` to its validation rubric (hard-coded for Phase A; admin-editable in a later phase). Only Extraction topics specced; other prompt types return a 501-style "topic list not yet available" response.

4. **`POST /prompts/briefs/validate-topic` endpoint** — request/response shapes per `CHECKLIST_DESIGN.md` §B4. Single shared system prompt with `=== TOPIC ===` switch. Sibling context accepted on the request. Anti-drift rule explicit in the system prompt.

5. **Schema: `ai_platform` + `output_destination` fields** — new nullable columns on `prompts` table via the established `a834c0e` pattern (models.py + migrations.py + 001_initial.sql). Corresponding additions to `GenerateRequest` / `PromptCreate` Pydantic schemas. `deployment_target` column stays for back-compat, populated in parallel with `ai_platform`.

6. **Pre-build test: Haiku vs Sonnet for per-topic validation** — run the 5-brief protocol in `CHECKLIST_DESIGN.md` §B5 before committing to a model in the endpoint implementation. Report findings in session output; pick the cheaper model if quality holds.

7. **Pre-build test: anti-drift rule holds** — 5-10 test briefs with deliberate sibling-topic gaps; observe whether Claude probes the focal topic only. Iterate phrasing if drift rate > 10%. Report findings before shipping the endpoint.

---

## Out of scope — do not build in Phase A

- **No UI.** `brief.js` is not touched in this session. The old prose-textarea Step 1 continues to work against the existing `/validate-brief` endpoint. `validate-topic` is callable only via direct API request in this phase.
- **No generator integration.** `GenerateRequest` may gain the two new fields, but `_briefSend` and `generator.js` are unchanged. `ai_platform` and `output_destination` are accepted by the generator endpoint but not yet emitted by any caller.
- **No prose-topic coaching implementation beyond the rubric scaffold.** The `validate-topic` endpoint returns shaped responses, but the per-topic rubrics (§B2 of design) are implemented as plain system-prompt fragments — no separate rubric registry, no admin editor. Hard-coded strings in a Python module.
- **No migration runner for in-progress briefs.** The code path for rehydrating legacy `step_answers` into the new topic shape is designed but not wired into `viewInits.brief` — that's a Phase B concern. Phase A only ensures new-shape writes are backward-compatible readers of legacy data.
- **No Prompt Type switch preview modal.** UI artefact. Phase B.
- **No "Mark complete" user override endpoint.** Defer — Phase A validates only via Claude. User override comes when UI lands in Phase B.
- **No deprecation of `/validate-brief`.** Lives in parallel until UI cutover.

---

## Required reconnaissance (before writing any code)

Read carefully and report findings on:

1. **`app/models.py` — `Brief` entity.** Confirm `step_answers` is TEXT and defaults to `"{}"`. Confirm no schema change is needed for the topic model (it's a JSON content change only). Confirm the `prompts` table has `deployment_target` and will accept two new nullable columns.

2. **`app/schemas.py`** — `BriefUpdate`, `BriefOut`, `GenerateRequest`, `PromptCreate`, `ValidateBriefRequest`, `ConversationEntry`. Confirm current shapes; identify additions needed for Phase A. Identify whether `ConversationEntry.topic_id` can be added as an optional field without breaking the existing filter in `validate_brief`.

3. **`app/routers/generation.py` — `validate_brief` endpoint.** Study the post-today conversation-history filtering pattern (`skipped=False` AND non-empty `question` AND `question not in {"validation","track"}`). `validate-topic` needs an analogous filter, scoped to `entry.topic_id == focal_topic_id`.

4. **`app/routers/briefs.py` — PATCH and GET handlers.** Confirm the existing `BriefUpdate` field-by-field handler pattern; `step_answers` updates go through this path. No changes to the PATCH handler required for Phase A if the JSON shape is caller-controlled, but confirm.

5. **`migrations/001_initial.sql` + `app/migrations.py` — `a834c0e` pattern.** Reconfirm the three-file add-column pattern used in Slot A1 / Slot T1 step B. Two new nullable columns on `prompts` must land via this pattern.

6. **Anthropic SDK usage** — look for an existing place where `model=` is chosen per call. Identify the env var (`ANTHROPIC_MODEL`) and confirm whether a call-site override (`claude-haiku-4-5-20251001`) can be passed without any infrastructure change. Phase A's Haiku test depends on this.

7. **Test infrastructure** — review `tests/test_generation.py` for the mock pattern (`mock_client = MagicMock()`, `mock_client.messages.create.return_value = mock_response`). Phase A will add tests for `validate-topic` using the same mock pattern.

---

## Expected plan output (before any code)

After reconnaissance, produce a short plan (≤20 lines) covering:

- **Data model changes**: exact JSON shape for a topic record within `step_answers`; whether a Pydantic model for a single topic (`BriefTopicEntry`) is added to `app/schemas.py` or kept as a dict-typed value.
- **Endpoint plumbing**: new file or addition to `generation.py`? URL routing? Response model class (probably new `ValidateTopicResponse`). Request model (`ValidateTopicRequest`). Where the shared system-prompt constant lives.
- **Topic rubric registry**: hard-coded Python dict mapping `topic_id` → rubric fragment (inserted into the shared system prompt at the `=== TOPIC ===` marker). Proposal: a new module `services/topic_rubrics.py`. Phase A implements only the 11 Extraction topics.
- **Haiku-test harness**: how and where the pre-build test runs. Suggestion: a standalone script in `scripts/test_haiku_vs_sonnet.py` that the developer runs by hand; results captured in the session summary.
- **Anti-drift test harness**: same structure; `scripts/test_anti_drift.py`. Results captured.
- **Migrations / schema plumbing**: the three-file pattern for the two new columns. Names confirmed (`ai_platform`, `output_destination`). Column types (VARCHAR).
- **Tests to add**: `tests/test_validate_topic.py` — happy paths for structured topics (`topic_1_prompt_type`), prose topics (`topic_6_data_points`), sibling-context plumbing, stale-seq-less behaviour (this is a stateless API call; no seq guard on server), response shape validation. Mock Claude responses.
- **Known deferrals and their hooks**: where the Phase B UI will plug in; what the Phase A code leaves as `TODO(phase-b)` comments.
- **Edge cases named before code**: e.g. empty sibling_answers; unknown `topic_id`; request where `prompt_type` doesn't match a defined rubric set.

Stop at the plan. Wait for APPROVED.

---

## Fast mode operating rules (this session)

Applies to Phase A build once the plan is approved:

1. **Plan review stays.** After reconnaissance, the plan is presented and approved before code.
2. **After APPROVED, execute end-to-end.** Edit files, run tests, run the Haiku and anti-drift pre-build tests, commit, push. No per-edit approval. No COMMIT READY gates. No asking before pytest.
3. **If tests fail at any point, stop and report.** Do not commit failing code.
4. **If the task requires changes outside Phase A scope** — any UI change, any compliance/guardrails change, any auth or audit_log change — stop and ask. This mode is for contained backend + test work.
5. **After push, report:** commit hash, test pass count, pre-build test results (Haiku vs Sonnet: agreement rate, recommendation; anti-drift: drift rate, recommendation), Railway deploy status if visible.
6. **Schema changes are allowed** in this phase (`ai_platform`, `output_destination` columns) because they're part of the declared scope and follow an established pattern. Any other schema change (new tables, FK changes, trigger changes) → stop and ask.
7. **`pytest` is the gate.** All existing tests must pass. New tests added in this phase must pass.
8. **Pre-build tests are gates too.** If Haiku's agreement rate is < 90%, default to Sonnet and note in the session summary. If anti-drift rule fails > 10% of test cases, iterate the phrasing once; if still failing, ship with Sonnet and a note that drift is a known residual risk.

---

## Acceptance criteria for Phase A

1. `POST /prompts/briefs/validate-topic` returns correctly shaped responses for all 11 Extraction topics (1, 2, 3, 4, 4b, 5, 6, 7, 8, 9, 10).
2. Sibling context is accepted on the request and referenced in Claude calls; anti-drift rule is honoured (tested).
3. `GenerateRequest` and `PromptCreate` accept `ai_platform` and `output_destination`. `prompts` table has both columns. Existing `deployment_target` still works.
4. Full test suite passes (count = current 105 + new tests added).
5. Haiku vs Sonnet test results documented.
6. Anti-drift test results documented.
7. No UI changes. No `brief.js` / `generator.js` / HTML changes.
8. PHASE2.md section 8 (Brief Builder checklist) updated with a "Phase A shipped — date" line if appropriate.

---

## Session opening message (to paste into Claude Code)

```
Task: Build Session A — topic model and validate-topic endpoint.

Context: docs/CHECKLIST_DESIGN.md is the authoritative design.
docs/BUILD_SESSION_A_BRIEF.md is the session scope and fast-mode
rules. Read both before starting.

Scope this session: Phase A only.
- Topic model on Brief.step_answers (new JSON shape,
  backward-compatible)
- State machine per topic (red/amber/green, persisted)
- Topic-to-validation rubric registry (hard-coded Extraction
  topics only)
- POST /prompts/briefs/validate-topic endpoint with sibling
  context and anti-drift system-prompt rule
- Two new columns on prompts: ai_platform, output_destination
  (a834c0e pattern; deployment_target stays for back-compat)
- Pre-build tests: Haiku vs Sonnet (cheaper if quality holds)
  and anti-drift (iterate phrasing if > 10% drift)
- Tests in tests/test_validate_topic.py

Do NOT build in this session: UI changes, brief.js changes,
generator integration, Prompt Type switch modal, Mark-complete
override endpoint, deprecation of /validate-brief, migration
of legacy briefs.

Fast mode rules apply (see brief §Fast mode operating rules).

Environment check first:
- pwd
- git log --oneline -3
- git status

Then reconnaissance per §Required reconnaissance in the brief.

Then short plan (≤20 lines) covering the §Expected plan output
items.

Stop at the plan. Wait for APPROVED before writing code.
```

---

## Revision log

- **Initial draft:** produced in design session following 19 April roadmap consolidation. Companion to `docs/CHECKLIST_DESIGN.md`.
