-- Prompt Registry — Initial Schema
-- Postgres-compatible reference migration.
-- For local development SQLite is used; this file is the production target.
-- Run once against a clean Postgres database.

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ── users ─────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    email           TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('Author','Approver','Auditor','Admin','SuperAdmin')),
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

-- ── scoring_dimensions ────────────────────────────────────────────────────────
CREATE TABLE scoring_dimensions (
    dimension_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    code                TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    framework           TEXT NOT NULL CHECK (framework IN ('REGULATORY','OWASP','NIST','ISO42001')),
    source_reference    TEXT,
    description         TEXT NOT NULL,
    score_5_criteria    TEXT NOT NULL,
    score_3_criteria    TEXT NOT NULL,
    score_1_criteria    TEXT NOT NULL,
    is_mandatory        BOOLEAN NOT NULL DEFAULT FALSE,
    blocking_threshold  INTEGER NOT NULL DEFAULT 2,
    applies_to_types    TEXT NOT NULL DEFAULT '[]',
    applies_if          TEXT,
    scoring_type        TEXT NOT NULL CHECK (scoring_type IN ('Blocking','Advisory','Maturity','Alignment')),
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INTEGER NOT NULL DEFAULT 0
);

-- ── injection_patterns ────────────────────────────────────────────────────────
CREATE TABLE injection_patterns (
    pattern_id    TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    category      TEXT NOT NULL CHECK (category IN (
                      'Instruction override','Persona hijack','Exfiltration',
                      'Delimiter attack','Unicode manipulation','Structural anomaly')),
    pattern_text  TEXT NOT NULL,
    match_type    TEXT NOT NULL CHECK (match_type IN ('substring','regex','unicode_range')),
    severity      TEXT NOT NULL CHECK (severity IN ('Critical','High','Medium')),
    description   TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    source        TEXT NOT NULL CHECK (source IN ('OWASP_ATLAS','MITRE_ATLAS','INTERNAL'))
);

-- ── prompts ───────────────────────────────────────────────────────────────────
CREATE TABLE prompts (
    prompt_id            TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    title                TEXT NOT NULL,
    prompt_type          TEXT NOT NULL CHECK (prompt_type IN (
                             'Governance','Analysis','Comms','Classification',
                             'Summarisation','Extraction','Comparison','Risk Review')),
    deployment_target    TEXT NOT NULL,
    input_type           TEXT NOT NULL,
    output_type          TEXT NOT NULL,
    risk_tier            TEXT NOT NULL CHECK (risk_tier IN ('Minimal','Limited','High','Prohibited')),
    owner_id             TEXT NOT NULL REFERENCES users(user_id),
    approver_id          TEXT REFERENCES users(user_id),
    status               TEXT NOT NULL DEFAULT 'Draft'
                             CHECK (status IN ('Draft','Active','Review Required','Suspended','Retired')),
    review_cadence_days  INTEGER NOT NULL DEFAULT 365,
    next_review_date     TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── upgrade_proposals ─────────────────────────────────────────────────────────
-- source_version_id and resulting_version_id reference prompt_versions.
-- Declared here without FK to break the circular dependency; FK added below.
CREATE TABLE upgrade_proposals (
    proposal_id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    prompt_id                  TEXT REFERENCES prompts(prompt_id),
    source_version_id          TEXT,
    proposed_at                TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    proposed_by                TEXT NOT NULL DEFAULT 'SYSTEM',
    status                     TEXT NOT NULL DEFAULT 'Pending'
                                   CHECK (status IN ('Pending','Partially Accepted','Accepted',
                                                     'Rejected','Applied','Abandoned')),
    inferred_purpose           TEXT,
    inferred_prompt_type       TEXT,
    inferred_risk_tier         TEXT,
    classification_confidence  TEXT CHECK (classification_confidence IN ('Low','Medium','High')),
    findings                   TEXT,
    suggestions                TEXT,
    user_responses             TEXT,
    responses_recorded_at      TIMESTAMPTZ,
    resulting_version_id       TEXT,
    applied_at                 TIMESTAMPTZ,
    applied_by                 TEXT REFERENCES users(user_id),
    abandoned_reason           TEXT
);

-- ── compliance_checks ─────────────────────────────────────────────────────────
-- version_id references prompt_versions; declared without FK here, added below.
CREATE TABLE compliance_checks (
    check_id                 TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    version_id               TEXT NOT NULL,
    job_id                   TEXT,
    run_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_by                   TEXT NOT NULL,
    overall_result           TEXT CHECK (overall_result IN ('Pass','Pass with warnings','Fail')),
    scores                   TEXT,
    blocking_defects         INTEGER NOT NULL DEFAULT 0,
    gold_standard            TEXT,
    flags                    TEXT,
    human_reviewed_by        TEXT REFERENCES users(user_id),
    human_reviewed_at        TIMESTAMPTZ,
    human_review_notes       TEXT,
    output_validation_result TEXT
);

-- ── compliance_check_jobs ─────────────────────────────────────────────────────
CREATE TABLE compliance_check_jobs (
    job_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    version_id    TEXT NOT NULL,
    requested_by  TEXT NOT NULL REFERENCES users(user_id),
    requested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status        TEXT NOT NULL DEFAULT 'Queued'
                      CHECK (status IN ('Queued','Running','Complete','Failed')),
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    result_id     TEXT REFERENCES compliance_checks(check_id),
    error_message TEXT,
    force_refresh BOOLEAN NOT NULL DEFAULT FALSE
);

-- ── prompt_versions ───────────────────────────────────────────────────────────
CREATE TABLE prompt_versions (
    version_id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    prompt_id              TEXT NOT NULL REFERENCES prompts(prompt_id),
    version_number         INTEGER NOT NULL,
    previous_version_id    TEXT REFERENCES prompt_versions(version_id),
    prompt_text            TEXT NOT NULL,
    change_summary         TEXT,
    defects_found          TEXT NOT NULL DEFAULT '[]',
    corrections_made       TEXT NOT NULL DEFAULT '[]',
    compliance_check_id    TEXT REFERENCES compliance_checks(check_id),
    regulatory_scores      TEXT,
    cache_valid            BOOLEAN NOT NULL DEFAULT TRUE,
    upgrade_proposal_id    TEXT REFERENCES upgrade_proposals(proposal_id),
    injection_scan_result  TEXT,
    created_by             TEXT NOT NULL REFERENCES users(user_id),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by            TEXT REFERENCES users(user_id),
    approved_at            TIMESTAMPTZ,
    is_active              BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (prompt_id, version_number)
);

-- ── audit_log ─────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    log_id       TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    timestamp    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id      TEXT,
    action       TEXT NOT NULL CHECK (action IN (
                     'Created','Edited','Activated','Retired','ComplianceChecked',
                     'Approved','DefectLogged','Corrected','InjectionDetected',
                     'ValidationFailed','Accessed','PromptImported','UpgradeProposed',
                     'UpgradeResponseRecorded','UpgradeApplied','UpgradeAbandoned',
                     'ClassificationOverridden')),
    entity_type  TEXT NOT NULL CHECK (entity_type IN (
                     'Prompt','PromptVersion','ComplianceCheck','User','UpgradeProposal')),
    entity_id    TEXT NOT NULL,
    detail       TEXT,
    ip_address   TEXT,
    session_id   TEXT,
    resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at  TIMESTAMPTZ,
    resolved_by  TEXT REFERENCES users(user_id)
);

-- ── Deferred foreign keys (circular references) ───────────────────────────────
ALTER TABLE upgrade_proposals
    ADD CONSTRAINT fk_up_source_version
        FOREIGN KEY (source_version_id) REFERENCES prompt_versions(version_id),
    ADD CONSTRAINT fk_up_resulting_version
        FOREIGN KEY (resulting_version_id) REFERENCES prompt_versions(version_id);

ALTER TABLE compliance_checks
    ADD CONSTRAINT fk_cc_version
        FOREIGN KEY (version_id) REFERENCES prompt_versions(version_id);

ALTER TABLE compliance_check_jobs
    ADD CONSTRAINT fk_ccj_version
        FOREIGN KEY (version_id) REFERENCES prompt_versions(version_id);

-- ── Indexes ───────────────────────────────────────────────────────────────────
-- Only one active version per prompt
CREATE UNIQUE INDEX idx_one_active_version_per_prompt
    ON prompt_versions (prompt_id)
    WHERE is_active = TRUE;

-- ── Trigger: AuditLog timestamp set at DB level ───────────────────────────────
CREATE OR REPLACE FUNCTION fn_set_audit_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.timestamp := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_log_timestamp
    BEFORE INSERT ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_set_audit_timestamp();

-- ── Trigger: AuditLog — prevent deletion ─────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_prevent_audit_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AuditLog records cannot be deleted';
END;
$$;

CREATE TRIGGER trg_prevent_audit_log_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_delete();

-- ── Trigger: AuditLog — prevent core field updates ───────────────────────────
CREATE OR REPLACE FUNCTION fn_prevent_audit_core_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.log_id      IS DISTINCT FROM NEW.log_id      OR
       OLD.timestamp   IS DISTINCT FROM NEW.timestamp   OR
       OLD.user_id     IS DISTINCT FROM NEW.user_id     OR
       OLD.action      IS DISTINCT FROM NEW.action      OR
       OLD.entity_type IS DISTINCT FROM NEW.entity_type OR
       OLD.entity_id   IS DISTINCT FROM NEW.entity_id   OR
       OLD.detail      IS DISTINCT FROM NEW.detail
    THEN
        RAISE EXCEPTION 'AuditLog core fields are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_audit_log_core_update
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_core_update();

-- ── Trigger: PromptVersion — prevent deletion ─────────────────────────────────
CREATE OR REPLACE FUNCTION fn_prevent_pv_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'PromptVersion records cannot be deleted';
END;
$$;

CREATE TRIGGER trg_prevent_prompt_version_delete
    BEFORE DELETE ON prompt_versions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_pv_delete();

-- ── Trigger: PromptVersion — prevent immutable content field updates ──────────
CREATE OR REPLACE FUNCTION fn_prevent_pv_content_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.prompt_text            IS DISTINCT FROM NEW.prompt_text            OR
       OLD.version_number         IS DISTINCT FROM NEW.version_number         OR
       OLD.prompt_id              IS DISTINCT FROM NEW.prompt_id              OR
       OLD.previous_version_id    IS DISTINCT FROM NEW.previous_version_id    OR
       OLD.created_by             IS DISTINCT FROM NEW.created_by             OR
       OLD.created_at             IS DISTINCT FROM NEW.created_at
    THEN
        RAISE EXCEPTION 'PromptVersion content fields are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_prompt_version_content_update
    BEFORE UPDATE ON prompt_versions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_pv_content_update();

-- ── Trigger: ScoringDimension update — invalidate compliance cache ────────────
CREATE OR REPLACE FUNCTION fn_invalidate_cache_on_dimension_update()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    UPDATE prompt_versions
    SET cache_valid = FALSE
    WHERE compliance_check_id IS NOT NULL;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_invalidate_cache_on_dimension_update
    AFTER UPDATE ON scoring_dimensions
    FOR EACH ROW EXECUTE FUNCTION fn_invalidate_cache_on_dimension_update();
