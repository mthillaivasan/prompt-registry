# AUDIT.md — Structural Review

**Date:** 2026-04-18
**Scope:** Static analysis of all application files. No edits, no queries, no migrations.
**Codebase:** Built across Sessions 1-5 (16 Apr), patched for Railway/Supabase deployment (17 Apr).

---

## 1. REPOSITORY MAP

### `app/`

| File | Lines | Description | Flags |
|------|-------|-------------|-------|
| `__init__.py` | 0 | Empty package marker | |
| `main.py` | 105 | FastAPI app factory, lifespan startup, router mounting, audit-log endpoint | MIXED — audit-log endpoint belongs in a router |
| `models.py` | 397 | All 12 SQLAlchemy ORM models | |
| `schemas.py` | 337 | All Pydantic request/response schemas | |
| `database.py` | 71 | Engine creation, session factory, SQLite/Postgres branching | |
| `dependencies.py` | 53 | `get_current_user` JWT dependency | |
| `auth.py` | 44 | Password hashing, JWT create/decode | |
| `migrations.py` | 94 | Runtime DDL: adds missing columns/tables on startup | |
| `triggers.py` | 103 | SQLite-syntax triggers and indexes, applied on startup | |
| `seed.py` | 467 | Idempotent seeding of users, dimensions, patterns, components, templates | LARGE |

### `app/routers/`

| File | Lines | Description | Flags |
|------|-------|-------------|-------|
| `__init__.py` | 0 | Empty package marker | |
| `auth.py` | 83 | Login, token refresh | |
| `health.py` | 24 | Health check endpoint | |
| `briefs.py` | 224 | Brief CRUD: create, update, list, get, step save, skip, complete, abandon | |
| `compliance.py` | 231 | Compliance check submit/poll, dimension listing, tier-2 trigger logic, applicable dimensions | MIXED — `_check_tier2_trigger` is business logic used by both compliance and prompts routers |
| `prompts.py` | 646 | Prompt CRUD, brief validation (Claude), brief scoring, brief restructuring, prompt generation (Claude) | LARGE, MIXED — contains 5 distinct responsibilities: prompt CRUD, brief validation, brief scoring, brief restructuring, prompt generation |
| `templates.py` | 105 | Component and template library listing | |
| `upgrade.py` | 268 | Import/upgrade pipeline: analyse, respond, apply, abandon | |
| `versions.py` | 195 | Prompt version CRUD: create, list, get, activate | |

### `services/`

| File | Lines | Description | Flags |
|------|-------|-------------|-------|
| `__init__.py` | 0 | Empty package marker | |
| `compliance_engine.py` | 337 | Compliance check execution: scoring, anomaly detection, gold standard, cache, job lifecycle | |
| `upgrade_engine.py` | 446 | Import analysis pipeline: injection scan, Claude analysis, response recording, proposal apply | LARGE |
| `injection_scanner.py` | 153 | Pattern-based injection detection with caching | |
| `prompt_components.py` | 758 | Hardcoded component text: input handlers, output handlers, regulatory guardrails, behaviour guardrails, template assembly | LARGE — all component text is inline Python dicts, duplicated from seed data |

### `static/`

| File | Lines | Description | Flags |
|------|-------|-------------|-------|
| `base.html` | 653 | SPA shell: CSS, auth, router, help system | LARGE, MIXED — CSS, JS framework, help content all in one file |
| `views/dashboard.js` | 99 | Dashboard view with prompt table and brief cards | |
| `views/detail.js` | 202 | Prompt detail with version history and compliance results | |
| `views/generator.js` | 243 | Prompt creation form with AI generation | |
| `views/brief.js` | 744 | 6-step Brief Builder with validation, scoring, guardrails | LARGE |
| `views/templates.js` | 52 | Template library grid view | |
| `views/import.js` | 192 | Import & Upgrade UI | |
| `views/audit.js` | 107 | Audit log table view | |

### `tests/`

| File | Lines | Description |
|------|-------|-------------|
| `conftest.py` | 98 | Fixtures: fresh DB per test, test users, auth headers |
| `test_prompts.py` | 378 | Prompt CRUD, version, activation tests (37 tests) |
| `test_compliance.py` | 285 | Compliance engine, scoring, cache tests (17 tests) |
| `test_upgrade.py` | 362 | Import/upgrade pipeline tests (14 tests) |
| `test_injection_scanner.py` | 145 | Injection scanner tests (13 tests) |

### `migrations/`

| File | Lines | Description |
|------|-------|-------------|
| `001_initial.sql` | 296 | Postgres reference schema with triggers and constraints |

### Root files

| File | Description |
|------|-------------|
| `Dockerfile` | Container build |
| `docker-compose.yml` | Local dev compose |
| `requirements.txt` | Python dependencies |
| `prompt_registry.db` | SQLite database (dev) |
| `PHASE2.md` | Phase 2 planning doc |
| `README.md` | Project readme |

---

## 2. DATA MODEL

### Models and Columns

**User** (`users`)
- `user_id` (PK), `email` (unique), `name`, `role`, `password_hash`, `is_active`, `created_at`, `last_login_at`
- Check: `role IN ('Maker','Checker','Admin')`

**ScoringDimension** (`scoring_dimensions`)
- `dimension_id` (PK), `code` (unique), `name`, `framework`, `source_reference`, `description`, `score_5_criteria`, `score_3_criteria`, `score_1_criteria`, `is_mandatory`, `blocking_threshold`, `applies_to_types`, `applies_if`, `scoring_type`, `is_active`, `sort_order`, `tier`, `tier2_trigger`
- `tier` and `tier2_trigger` added post-Session 1 via `migrations.py`

**InjectionPattern** (`injection_patterns`)
- `pattern_id` (PK), `category`, `pattern_text`, `match_type`, `severity`, `description`, `is_active`, `source`

**Prompt** (`prompts`)
- `prompt_id` (PK), `title`, `prompt_type`, `deployment_target`, `input_type`, `output_type`, `risk_tier`, `owner_id` (FK users), `approver_id` (FK users), `status`, `review_cadence_days`, `next_review_date`, `created_at`, `updated_at`

**PromptVersion** (`prompt_versions`)
- `version_id` (PK), `prompt_id` (FK prompts), `version_number`, `previous_version_id` (self-FK), `prompt_text`, `change_summary`, `defects_found`, `corrections_made`, `compliance_check_id` (string, circular FK), `regulatory_scores`, `cache_valid`, `upgrade_proposal_id` (string, circular FK), `injection_scan_result`, `created_by` (FK users), `created_at`, `approved_by` (FK users), `approved_at`, `is_active`
- Unique: (`prompt_id`, `version_number`)

**UpgradeProposal** (`upgrade_proposals`)
- `proposal_id` (PK), `prompt_id` (FK prompts), `source_version_id` (string), `proposed_at`, `proposed_by`, `status`, `inferred_purpose`, `inferred_prompt_type`, `inferred_risk_tier`, `classification_confidence`, `findings` (JSON), `suggestions` (JSON), `user_responses` (JSON), `responses_recorded_at`, `resulting_version_id` (string), `applied_at`, `applied_by` (FK users), `abandoned_reason`

**ComplianceCheck** (`compliance_checks`)
- `check_id` (PK), `version_id` (string), `job_id` (string), `run_at`, `run_by`, `overall_result`, `scores` (JSON), `blocking_defects`, `gold_standard` (JSON), `flags` (JSON), `human_reviewed_by` (FK users), `human_reviewed_at`, `human_review_notes`, `output_validation_result` (JSON)

**ComplianceCheckJob** (`compliance_check_jobs`)
- `job_id` (PK), `version_id` (string), `requested_by` (FK users), `requested_at`, `status`, `started_at`, `completed_at`, `result_id` (FK compliance_checks), `error_message`, `force_refresh`

**AuditLog** (`audit_log`)
- `log_id` (PK), `timestamp` (server_default), `user_id`, `action`, `entity_type`, `entity_id`, `detail` (JSON), `ip_address`, `session_id`, `resolved`, `resolved_at`, `resolved_by` (FK users)

**Brief** (`briefs`)
- `brief_id` (PK), `status`, `quality_score`, `step_progress`, `client_name`, `business_owner_name`, `business_owner_role`, `brief_builder_id` (FK users), `interviewer_id` (FK users), `step_answers` (JSON), `selected_guardrails` (JSON), `restructured_brief`, `created_at`, `updated_at`, `submitted_at`, `resulting_prompt_id` (FK prompts)
- Added post-Session 1 via `migrations.py`

**PromptComponent** (`prompt_components`)
- `component_id` (PK), `code` (unique), `category`, `name`, `description`, `component_text`, `example_output`, `applicable_dimensions` (JSON), `is_active`, `sort_order`
- Added post-Session 1 via `migrations.py`

**PromptTemplate** (`prompt_templates`)
- `template_id` (PK), `code` (unique), `name`, `description`, `use_case`, `prompt_type`, `risk_tier`, `input_type`, `output_type`, `component_codes` (JSON), `prompt_text`, `output_example`, `gold_standard_grade`, `applicable_to_client_types`, `is_active`, `sort_order`
- Added post-Session 1 via `migrations.py`

### Schema Drift Analysis (F1)

**CRITICAL — `users.role` check constraint mismatch:**
- SQLAlchemy model: `('Maker','Checker','Admin')`
- `001_initial.sql`: `('Author','Approver','Auditor','Admin','SuperAdmin')`
- Impact: If `001_initial.sql` was run against Supabase Postgres, the seed user with role `'Admin'` would succeed (present in both), but any user created with role `'Maker'` or `'Checker'` via the API would be rejected by the Postgres CHECK constraint. If the SQL was never run and `Base.metadata.create_all()` was used instead, the SQLAlchemy check constraint would be active and Postgres would have `('Maker','Checker','Admin')`.
- Cannot determine from code alone which path was taken on Supabase.

**CRITICAL — `audit_log.action` check constraint mismatch:**
- SQLAlchemy model includes 8 actions not in `001_initial.sql`: `PromptGenerated`, `BriefCreated`, `BriefUpdated`, `BriefAbandoned`, `BriefCompleted`, `BriefStepSkipped`, `BriefQuestionSkipped`, `BriefTrackAbandoned`, `TokenRefreshed`
- Impact: If the SQL check constraint is active on Postgres, any brief operation or token refresh would fail with a constraint violation.

**CRITICAL — `audit_log.entity_type` check constraint mismatch:**
- SQLAlchemy model includes `'Brief'`, SQL does not.
- Impact: All brief-related audit entries would fail on Postgres if the SQL constraint is active.

**HIGH — Missing tables in `001_initial.sql`:**
- `briefs`, `prompt_components`, `prompt_templates` are not in the reference SQL.
- `migrations.py` creates them with `CREATE TABLE IF NOT EXISTS` but without CHECK constraints or foreign keys.
- Impact: On Postgres, these tables exist but lack referential integrity constraints present in the SQLAlchemy model.

**HIGH — Missing columns in `001_initial.sql`:**
- `scoring_dimensions.tier` and `scoring_dimensions.tier2_trigger` not in SQL.
- `migrations.py` adds them with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- Impact: Likely resolved by migrations.py, but the reference SQL is stale.

**HIGH — Triggers are SQLite-only at runtime:**
- `triggers.py` uses SQLite trigger syntax (`CREATE TRIGGER IF NOT EXISTS ... BEGIN ... END`).
- On Postgres, `create_triggers_and_indexes()` will fail, but the error is swallowed by the `try/except` in `main.py` lifespan.
- `001_initial.sql` has equivalent Postgres triggers, but if it was not run, **Postgres has no immutability triggers**.
- Impact: `PromptVersion` and `AuditLog` immutability is not enforced on Supabase Postgres.

**MEDIUM — Date type mismatch:**
- SQLAlchemy stores all dates as `String` (ISO 8601 text).
- `001_initial.sql` uses `TIMESTAMPTZ`.
- If `create_all()` ran on Postgres, columns would be `VARCHAR` not `TIMESTAMPTZ`.
- Impact: Sorting and comparison of dates as strings is fragile. No timezone enforcement.

**MEDIUM — `AuditLog.timestamp` server_default:**
- SQLAlchemy: `server_default=text("(strftime('%Y-%m-%dT%H:%M:%SZ','now'))")` — SQLite function.
- On Postgres via `create_all()`, this `strftime` call would fail or be ignored.
- `001_initial.sql` uses `DEFAULT NOW()` and a trigger — correct for Postgres, but only if the SQL was run.

---

## 3. API SURFACE

### Auth

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| POST | `/auth/login` | `OAuth2PasswordRequestForm` (username, password) | `{access_token, token_type}` | `auth.py` |
| POST | `/auth/refresh` | Bearer token | `{access_token, token_type}` | `auth.py` |

### Health

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| GET | `/health` | None (no auth) | `{status, database, anthropic_key_set, anthropic_key_prefix}` | `health.py` |

**Flag:** Health endpoint leaks first 15 chars of the Anthropic API key. This is a security concern in production.

### Prompts

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| POST | `/prompts` | `PromptCreate` | `PromptDetail` (201) | `prompts.py` |
| GET | `/prompts` | Query params: status, risk_tier, prompt_type, owner_id, search | `list[PromptOut]` | `prompts.py` |
| GET | `/prompts/{id}` | — | `PromptDetail` | `prompts.py` |
| PATCH | `/prompts/{id}` | `PromptUpdate` | `PromptDetail` | `prompts.py` |
| POST | `/prompts/validate-brief` | `ValidateBriefRequest` | `ValidateBriefResponse` | `prompts.py` |
| POST | `/prompts/briefs/check-relevance` | `dict` (untyped) | `{result: str}` | `prompts.py` |
| POST | `/prompts/briefs/score` | `BriefScoreRequest` | `BriefScoreResponse` | `prompts.py` |
| POST | `/prompts/briefs/restructure` | `RestructureBriefRequest` | `RestructureBriefResponse` | `prompts.py` |
| POST | `/prompts/generate` | `GenerateRequest` | `GenerateResponse` | `prompts.py` |
| POST | `/prompts/analyse` | `AnalyseRequest` | `AnalyseResponse` (202) | `upgrade.py` |

**Flag — `/prompts/briefs/check-relevance`:** Request body is untyped `dict`, not a Pydantic model. No validation.

**Flag — `/prompts/validate-brief` error path:** On any exception (Claude API error, JSON parse error, network timeout), the endpoint returns `ValidateBriefResponse(tier=1, accepted=True)` — silently accepting the brief. This is F2.

**Flag — `/prompts/briefs/restructure` error path:** On any exception, returns the original text unchanged. Not an error, but the user is not notified.

### Versions

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| POST | `/prompts/{id}/versions` | `VersionCreate` | `PromptVersionOut` (201) | `versions.py` |
| GET | `/prompts/{id}/versions` | — | `list[PromptVersionOut]` | `versions.py` |
| GET | `/prompts/{id}/versions/{vid}` | — | `PromptVersionOut` | `versions.py` |
| POST | `/prompts/{id}/versions/{vid}/activate` | — | `PromptVersionOut` | `versions.py` |

### Briefs

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| POST | `/briefs` | `BriefCreate` | `BriefOut` (201) | `briefs.py` |
| GET | `/briefs` | Query: status | `list[BriefOut]` | `briefs.py` |
| GET | `/briefs/{id}` | — | `BriefOut` | `briefs.py` |
| PATCH | `/briefs/{id}` | `BriefUpdate` | `BriefOut` | `briefs.py` |
| PATCH | `/briefs/{id}/step/{n}` | `BriefUpdate` | `BriefOut` | `briefs.py` |
| POST | `/briefs/{id}/skip-step/{n}` | — | `{ok: true}` | `briefs.py` |
| POST | `/briefs/{id}/complete` | — | `BriefOut` | `briefs.py` |
| POST | `/briefs/{id}/abandon` | — | `BriefOut` | `briefs.py` |

**Flag — `/briefs/{id}/skip-step/{n}`:** Response shape `{ok: true}` is inconsistent with all other brief endpoints that return `BriefOut`.

### Compliance

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| POST | `/compliance-checks` | `ComplianceCheckRequest` | `ComplianceJobOut` (202) | `compliance.py` |
| GET | `/compliance-checks/{job_id}` | — | `ComplianceJobOut` | `compliance.py` |
| GET | `/scoring-dimensions` | — | `list[dict]` (untyped) | `compliance.py` |
| GET | `/scoring-dimensions/applicable` | Query params | `{tier1, tier2, tier3}` (untyped) | `compliance.py` |

**Flag — `/scoring-dimensions` and `/scoring-dimensions/applicable`:** Responses are manually constructed dicts, not Pydantic models. Shape is not validated.

### Templates / Components

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| GET | `/components` | Query: category | `list[dict]` (untyped) | `templates.py` |
| GET | `/templates` | — | `list[dict]` (untyped) | `templates.py` |
| GET | `/templates/{id}` | — | `dict` (untyped) | `templates.py` |

**Flag — F3 likely cause:** If the `prompt_templates` table does not exist or has missing columns on Supabase (because `migrations.py` failed silently during startup), `GET /templates` would raise an unhandled SQLAlchemy error, returning 500 ISE. The `migrations.py` `_create_table_if_not_exists` wraps errors in `print()` but does not retry.

### Upgrade

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| GET | `/proposals/{id}` | — | `ProposalOut` | `upgrade.py` |
| POST | `/proposals/{id}/responses` | `UserResponseRequest` | `ProposalOut` | `upgrade.py` |
| POST | `/proposals/{id}/apply` | `ApplyRequest` (optional) | `ApplyResponse` | `upgrade.py` |
| POST | `/proposals/{id}/abandon` | `AbandonRequest` | `ProposalOut` | `upgrade.py` |
| GET | `/prompts/{id}/proposals` | — | `list[ProposalOut]` | `upgrade.py` |

### Audit Log

| Method | Path | Request | Response | Router |
|--------|------|---------|----------|--------|
| GET | `/audit-log` | Query: skip, limit, action | `list[dict]` (untyped) | `main.py` |

### Static

| Method | Path | Response | Router |
|--------|------|----------|--------|
| GET | `/` | `base.html` | `main.py` |
| GET | `/static/*` | Static files | `main.py` (mount) |

---

## 4. COUPLING AND DUPLICATION

### 4.1 `_utcnow()` defined 6 times

The same UTC timestamp helper is independently defined in:
- `app/models.py:24`
- `app/routers/prompts.py:34`
- `app/routers/briefs.py:18`
- `app/routers/upgrade.py:37`
- `app/routers/versions.py:19`
- `app/routers/auth.py:16`
- `services/compliance_engine.py:54`
- `services/upgrade_engine.py:110`

Not a bug, but if the format ever needs to change, 8 files must be updated.

### 4.2 `_check_tier2_trigger` lives in `compliance.py` but is imported by `prompts.py`

`app/routers/prompts.py:531` imports `_check_tier2_trigger` from `app/routers/compliance.py`. This creates a cross-router dependency. The function is business logic that should be in a service, not a router.

### 4.3 Component text duplicated between `prompt_components.py` and database

`services/prompt_components.py` contains all component text as hardcoded Python dicts (758 lines). `app/seed.py` copies this text into the `prompt_components` database table. The `GET /components` endpoint reads from the database, but `POST /prompts/generate` reads from the Python dicts via `assemble_template()`.

If a component is edited in the database, the generator ignores the change. If it's edited in the Python dict, the database is not updated (seed is idempotent — skips if rows exist).

**Concern:** Two sources of truth for the same data. Changes to one do not propagate to the other.

### 4.4 `_parse_json_response` / `_parse_json` duplicated

JSON response parsing with markdown fence stripping appears in:
- `services/compliance_engine.py:132` as `_parse_json_response`
- `services/upgrade_engine.py:124` as `_parse_json`
- `app/routers/prompts.py:351-353` (inline in `validate_brief`)

Same logic, three copies.

### 4.5 `_call_claude` duplicated

The Anthropic API call wrapper is independently defined in:
- `services/compliance_engine.py:121`
- `services/upgrade_engine.py:113`

Both are identical. `app/routers/prompts.py` constructs clients inline (4 separate `anthropic.Anthropic()` calls).

### 4.6 `ANOMALY_SYSTEM_PROMPT` duplicated

The anomaly detection prompt is defined identically in:
- `services/compliance_engine.py:39-50`
- `services/upgrade_engine.py:95-106`

### 4.7 Audit log action constraint must be updated in two places

Adding a new audit action requires changes to both:
- `app/models.py` (SQLAlchemy CHECK constraint, line 313-320)
- `migrations/001_initial.sql` (Postgres CHECK constraint, line 164-169)

These are already out of sync (see Section 2).

### 4.8 Brief-related endpoints split across two routers

Brief CRUD is in `app/routers/briefs.py` (`/briefs/*`), but brief validation, scoring, and restructuring are in `app/routers/prompts.py` (`/prompts/validate-brief`, `/prompts/briefs/score`, `/prompts/briefs/restructure`). The URL path `/prompts/briefs/...` is confusing — these are brief operations, not prompt operations.

---

## 5. BUG HOTSPOTS

### 5.1 `app/routers/prompts.py` (646 lines)

**Justification:** This file is the primary source of regression churn. It has 5 distinct responsibilities (prompt CRUD, brief validation, brief scoring, brief restructuring, prompt generation), each with its own Claude API integration and error handling. The silent-acceptance catch-all at line 372-374 (`except Exception: return ValidateBriefResponse(tier=1, accepted=True)`) is the root cause of F2.

Changes to any of the 5 features risk breaking the others because they share the same router namespace, and the file is too long (646 lines) for quick comprehension during a fix session.

The `_resolve_guardrails` function at line 529 imports from `compliance.py` at call time, creating a fragile cross-router dependency. The generate endpoint at line 557 imports from `services.injection_scanner` and `services.prompt_components` at call time inside the function body.

### 5.2 `app/migrations.py` (94 lines)

**Justification:** This file is responsible for making the database match the SQLAlchemy models when the code evolves faster than the reference SQL. Its `_add_column` function swallows all exceptions silently (`except Exception: pass`). Its `_create_table_if_not_exists` prints warnings but does not raise.

If a migration fails silently on Supabase startup, the app starts with missing tables or columns, causing ISEs later when endpoints try to query those tables. F3 (templates ISE) likely traces back to this file. The bug pattern is: fix code in one session, forget to update migrations, deploy, migrations silently fail, user hits ISE.

### 5.3 `app/triggers.py` (103 lines)

**Justification:** The triggers use SQLite syntax and are executed unconditionally on startup. On Postgres, they fail silently (caught by `main.py` lifespan try/except). This means:

1. `PromptVersion` immutability is not enforced on Postgres.
2. `AuditLog` immutability is not enforced on Postgres.
3. The partial unique index `idx_one_active_version_per_prompt` may not exist on Postgres.

The Postgres equivalents in `001_initial.sql` are correct, but there is no mechanism to verify they were applied. If someone deploys from scratch using only `create_all()` + `run_migrations()`, they get no triggers at all.

---

## 6. TEST COVERAGE HONESTY

**Total tests:** 91 (37 prompt, 17 compliance, 14 upgrade, 13 injection, plus fixture overhead)
**All tests run against SQLite**, not Postgres.

### F1: Schema drift between SQLAlchemy models and Supabase Postgres

**Would existing tests catch this?** No. All tests use SQLite via `conftest.py` (line 18: `DATABASE_URL = f"sqlite:///{_temp_db.name}"`). The role constraint mismatch (`Maker` vs `Author`), missing audit actions, and missing tables would only manifest on Postgres.

**Minimal test:** A test that creates the schema against a Postgres instance (e.g., Docker) and verifies: (a) seed data inserts succeed, (b) all audit log actions in the model's CHECK constraint exist in the database constraint, (c) all tables exist with expected columns.

### F2: Brief validation silently accepting all inputs

**Would existing tests catch this?** No. There are zero tests for the `/prompts/validate-brief` endpoint. The endpoint calls the Claude API, and no test mocks it or verifies the error path.

**Minimal test:** Two tests: (1) Mock Claude API to return a valid Tier 3 response, assert `accepted=False`. (2) Mock Claude API to raise an exception, assert the response is NOT `tier=1, accepted=True` (currently it is — the test would fail, proving the bug).

### F3: Templates endpoint ISE

**Would existing tests catch this?** No. There are zero tests for `GET /templates`, `GET /templates/{id}`, or `GET /components`. The templates router has no test file.

**Minimal test:** A test that calls `GET /templates` with auth headers and asserts status 200 and a non-empty list. If the `prompt_templates` table is missing or malformed, this test would return 500 and fail.

---

## 7. RISK REGISTER FOR THE NEXT FOUR DAYS

### R1: Schema drift causes data loss on Supabase deploy (HIGH)

**What could go wrong:** A redeploy triggers `create_all()` which tries to create tables that already exist with different constraints. Or a new feature adds an audit action that Postgres rejects. User operations fail silently or with 500 errors.
**Likelihood:** High — this is already happening (F1, F3).
**Recovery time:** 2-4 hours per incident. Diagnosing requires comparing SQLAlchemy models to actual Postgres schema, then writing ALTER TABLE statements.

### R2: Brief validation passes everything through to generation (HIGH)

**What could go wrong:** Users submit vague or injection-laden brief text, validation says "Tier 1, accepted," the generator produces a weak or compromised prompt. In a demo, the Brief Builder's quality gate — the key differentiator — does nothing.
**Likelihood:** High — this is the current state (F2). Any Claude API hiccup triggers the fallback.
**Recovery time:** 30 minutes to fix the catch-all. But if bad prompts have already been generated and saved, cleanup is manual.

### R3: Postgres has no immutability triggers (MEDIUM-HIGH)

**What could go wrong:** The demo claims "immutable audit trail" and "immutable prompt versions." On Supabase, neither is enforced. An auditor or regulator testing the claim could update or delete records.
**Likelihood:** Medium — unlikely to be tested during a 4-day demo, but high impact to credibility if discovered.
**Recovery time:** 1-2 hours to run the Postgres trigger SQL from `001_initial.sql`, after verifying the constraint mismatches are fixed first.

### R4: `prompt_components.py` and database diverge (MEDIUM)

**What could go wrong:** Someone edits a component in the database (or the seed adds new components), but the generator still uses the hardcoded Python dicts. The generated prompt doesn't match what the component library shows.
**Likelihood:** Medium — will surface the first time anyone modifies a component.
**Recovery time:** 1-2 hours to refactor `assemble_template()` to read from the database instead of Python dicts.

### R5: Background task DB session sharing (MEDIUM)

**What could go wrong:** `compliance_engine.run_compliance_check()` and `upgrade_engine._run_analysis_with_job()` receive the request's `db` session as a parameter and use it in a background task. FastAPI background tasks run after the response is sent, but the session may already be closed by the `get_db()` generator's `finally` block. This can cause `DetachedInstanceError` or stale reads.
**Likelihood:** Medium — depends on timing. More likely under load or slow Claude API responses.
**Recovery time:** 1-2 hours to create a new session inside the background task.

---

## 8. RECOMMENDATION

**(b) Refactor these specific files first, then proceed to F1/F2/F3.**

### Rationale

The codebase is functional and demoable, but the three critical bugs share a common root: `prompts.py` is doing too much, `migrations.py` fails silently, and there is no test coverage for the affected code paths. Fixing F1/F2/F3 directly without addressing the structural issues will likely continue the regression churn pattern — fixing one thing while breaking another.

However, with 4 days to demo, a full rebuild (option c) is not justified. The models, schemas, services, and test infrastructure are solid. The problems are concentrated in a small number of files.

### Refactor scope

| # | File | What to do | Estimate |
|---|------|-----------|----------|
| 1 | `app/routers/prompts.py` | Extract brief validation, brief scoring, brief restructuring, and generate into their own router (`app/routers/brief_validation.py` or similar). Move `_resolve_guardrails` to a service. This reduces `prompts.py` to ~200 lines (CRUD only) and isolates the Claude API dependencies. | 1.5 hours |
| 2 | `migrations/001_initial.sql` | Update to match current SQLAlchemy models: fix role constraint, add missing audit actions, add missing entity types, add `briefs`/`prompt_components`/`prompt_templates` tables, add `tier`/`tier2_trigger` columns. This becomes the authoritative schema. | 1 hour |
| 3 | `app/migrations.py` | After fixing the SQL, add proper error reporting (raise on failure instead of swallowing). Add a schema verification step that checks expected tables/columns exist after `create_all()` + `run_migrations()`. | 1 hour |
| 4 | `app/triggers.py` | Add Postgres-compatible trigger creation. Check `_is_sqlite` from `database.py` and use appropriate syntax per backend. Or: skip triggers.py entirely on Postgres and rely on `001_initial.sql` being run. | 1 hour |

**Total refactor: ~4.5 hours**

### Then fix F1/F2/F3

| Fix | What to do | Estimate |
|-----|-----------|----------|
| F1 | Run corrected `001_initial.sql` against Supabase (or write ALTER TABLE statements to reconcile). Verify with a schema comparison query. | 1 hour |
| F2 | Replace the catch-all `except Exception: return tier=1` with proper error handling that returns a 502 to the frontend, which can then show "Validation unavailable — try again." | 30 min |
| F3 | Verify `prompt_templates` table exists on Supabase with correct columns. If not, the corrected `migrations.py` should create it. Add a test. | 30 min |

### Then add test coverage

| Test | What to do | Estimate |
|------|-----------|----------|
| Brief validation | Mock Claude, test tiers 1/2/3, test error path | 1 hour |
| Templates endpoint | Test `GET /templates`, `GET /components` | 30 min |
| Schema verification | Test that all models' CHECK constraints match expected values | 1 hour |

**Total post-refactor work: ~4.5 hours**
**Grand total: ~9 hours of focused work before feature development.**

---

## Pass 1 oversights surfaced in production

1. **main.py lifespan try/except was swallowing migration failures** despite Pass 1 Task 2 making migrations.py loud. The error swallowing was one level up from where Pass 1 looked. Fixed in commit d7866cb (main.py: let startup failures crash instead of swallow).

2. **app/models.py AuditLog.timestamp used SQLite-specific strftime** as server_default, blocking Postgres create_all with "function strftime(unknown, unknown) does not exist". The audit flagged this in section 2 as MEDIUM severity, which was calibrated against demo risk, not production reliability. For a tool intended to run on Postgres in production, any finding flagged "will fail on Postgres" should be re-ranked HIGH.

3. **Lesson for Pass 2 scoping**: the audit's severity rankings were correct for their original framing (demo Tuesday) but need recalibration now that the goal is "tool that works properly long-term." Before starting Pass 2, re-read audit sections 2 and 5 and reclassify anything that will fail on Postgres as HIGH, not MEDIUM.
