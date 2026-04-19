-- Prompt Registry — Authoritative Schema
-- Postgres-compatible. Matches app/models.py exactly.
--
-- This file is the single source of truth for the production schema.
-- Run once against a clean Postgres database, or use the companion
-- reconciliation script (scripts/verify_schema.py) to detect drift.
--
-- Last synced with models.py: 2026-04-19

-- ── Extensions ────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLES — ordered to satisfy foreign key dependencies
-- ══════════════════════════════════════════════════════════════════════════════

-- ── users ─────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    user_id         TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    email           TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TEXT NOT NULL,
    last_login_at   TEXT,

    CONSTRAINT ck_users_role CHECK (role IN ('Maker','Checker','Admin'))
);

-- ── scoring_dimensions ────────────────────────────────────────────────────────
CREATE TABLE scoring_dimensions (
    dimension_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    code                TEXT UNIQUE NOT NULL,
    name                TEXT NOT NULL,
    framework           TEXT NOT NULL,
    source_reference    TEXT,
    description         TEXT NOT NULL,
    score_5_criteria    TEXT NOT NULL,
    score_3_criteria    TEXT NOT NULL,
    score_1_criteria    TEXT NOT NULL,
    is_mandatory        BOOLEAN NOT NULL DEFAULT FALSE,
    blocking_threshold  INTEGER NOT NULL DEFAULT 2,
    applies_to_types    TEXT NOT NULL DEFAULT '[]',
    applies_if          TEXT,
    scoring_type        TEXT NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    tier                INTEGER NOT NULL DEFAULT 3,
    tier2_trigger       TEXT,
    instructional_text  TEXT,
    updated_at          TEXT,
    updated_by          TEXT REFERENCES users(user_id),

    CONSTRAINT ck_sd_framework
        CHECK (framework IN ('REGULATORY','OWASP','NIST','ISO42001')),
    CONSTRAINT ck_sd_scoring_type
        CHECK (scoring_type IN ('Blocking','Advisory','Maturity','Alignment')),
    CONSTRAINT ck_sd_tier
        CHECK (tier IN (1, 2, 3))
);

-- ── injection_patterns ────────────────────────────────────────────────────────
CREATE TABLE injection_patterns (
    pattern_id    TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    category      TEXT NOT NULL,
    pattern_text  TEXT NOT NULL,
    match_type    TEXT NOT NULL,
    severity      TEXT NOT NULL,
    description   TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    source        TEXT NOT NULL,

    CONSTRAINT ck_ip_category
        CHECK (category IN (
            'Instruction override','Persona hijack','Exfiltration',
            'Delimiter attack','Unicode manipulation','Structural anomaly')),
    CONSTRAINT ck_ip_match_type
        CHECK (match_type IN ('substring','regex','unicode_range')),
    CONSTRAINT ck_ip_severity
        CHECK (severity IN ('Critical','High','Medium')),
    CONSTRAINT ck_ip_source
        CHECK (source IN ('OWASP_ATLAS','MITRE_ATLAS','INTERNAL'))
);

-- ── prompts ───────────────────────────────────────────────────────────────────
CREATE TABLE prompts (
    prompt_id            TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    title                TEXT NOT NULL,
    prompt_type          TEXT NOT NULL,
    deployment_target    TEXT NOT NULL,
    input_type           TEXT NOT NULL,
    output_type          TEXT NOT NULL,
    risk_tier            TEXT NOT NULL,
    owner_id             TEXT NOT NULL REFERENCES users(user_id),
    approver_id          TEXT REFERENCES users(user_id),
    status               TEXT NOT NULL DEFAULT 'Draft',
    review_cadence_days  INTEGER NOT NULL DEFAULT 365,
    next_review_date     TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,

    CONSTRAINT ck_prompts_risk_tier
        CHECK (risk_tier IN ('Minimal','Limited','High','Prohibited')),
    CONSTRAINT ck_prompts_status
        CHECK (status IN ('Draft','Active','Review Required','Suspended','Retired')),
    CONSTRAINT ck_prompts_type
        CHECK (prompt_type IN (
            'Governance','Analysis','Comms','Classification',
            'Summarisation','Extraction','Comparison','Risk Review'))
);

-- ── upgrade_proposals ─────────────────────────────────────────────────────────
-- source_version_id and resulting_version_id reference prompt_versions.
-- Declared here without FK to break the circular dependency; FK added below.
CREATE TABLE upgrade_proposals (
    proposal_id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    prompt_id                  TEXT REFERENCES prompts(prompt_id),
    source_version_id          TEXT,
    proposed_at                TEXT NOT NULL,
    proposed_by                TEXT NOT NULL DEFAULT 'SYSTEM',
    status                     TEXT NOT NULL DEFAULT 'Pending',
    inferred_purpose           TEXT,
    inferred_prompt_type       TEXT,
    inferred_risk_tier         TEXT,
    classification_confidence  TEXT,
    findings                   TEXT,
    suggestions                TEXT,
    user_responses             TEXT,
    responses_recorded_at      TEXT,
    resulting_version_id       TEXT,
    applied_at                 TEXT,
    applied_by                 TEXT REFERENCES users(user_id),
    abandoned_reason           TEXT,

    CONSTRAINT ck_up_status
        CHECK (status IN (
            'Pending','Partially Accepted','Accepted',
            'Rejected','Applied','Abandoned')),
    CONSTRAINT ck_up_confidence
        CHECK (classification_confidence IN ('Low','Medium','High')
               OR classification_confidence IS NULL)
);

-- ── compliance_checks ─────────────────────────────────────────────────────────
-- version_id references prompt_versions; declared without FK here, added below.
CREATE TABLE compliance_checks (
    check_id                 TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    version_id               TEXT NOT NULL,
    job_id                   TEXT,
    run_at                   TEXT NOT NULL,
    run_by                   TEXT NOT NULL,
    overall_result           TEXT,
    scores                   TEXT,
    blocking_defects         INTEGER NOT NULL DEFAULT 0,
    gold_standard            TEXT,
    flags                    TEXT,
    human_reviewed_by        TEXT REFERENCES users(user_id),
    human_reviewed_at        TEXT,
    human_review_notes       TEXT,
    output_validation_result TEXT,

    CONSTRAINT ck_cc_result
        CHECK (overall_result IN ('Pass','Pass with warnings','Fail')
               OR overall_result IS NULL)
);

-- ── compliance_check_jobs ─────────────────────────────────────────────────────
CREATE TABLE compliance_check_jobs (
    job_id        TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    version_id    TEXT NOT NULL,
    requested_by  TEXT NOT NULL REFERENCES users(user_id),
    requested_at  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'Queued',
    started_at    TEXT,
    completed_at  TEXT,
    result_id     TEXT REFERENCES compliance_checks(check_id),
    error_message TEXT,
    force_refresh BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT ck_ccj_status
        CHECK (status IN ('Queued','Running','Complete','Failed'))
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
    compliance_check_id    TEXT,
    regulatory_scores      TEXT,
    cache_valid            BOOLEAN NOT NULL DEFAULT TRUE,
    upgrade_proposal_id    TEXT,
    injection_scan_result  TEXT,
    created_by             TEXT NOT NULL REFERENCES users(user_id),
    created_at             TEXT NOT NULL,
    approved_by            TEXT REFERENCES users(user_id),
    approved_at            TEXT,
    is_active              BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_pv_prompt_version UNIQUE (prompt_id, version_number)
);

-- ── audit_log ─────────────────────────────────────────────────────────────────
CREATE TABLE audit_log (
    log_id       TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    timestamp    TEXT NOT NULL DEFAULT NOW()::TEXT,
    user_id      TEXT,
    action       TEXT NOT NULL,
    entity_type  TEXT NOT NULL,
    entity_id    TEXT NOT NULL,
    detail       TEXT,
    ip_address   TEXT,
    session_id   TEXT,
    resolved     BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at  TEXT,
    resolved_by  TEXT REFERENCES users(user_id),

    CONSTRAINT ck_al_action CHECK (action IN (
        'Created','Edited','Activated','Retired','ComplianceChecked',
        'Approved','DefectLogged','Corrected','InjectionDetected',
        'ValidationFailed','Accessed','PromptImported','UpgradeProposed',
        'UpgradeResponseRecorded','UpgradeApplied','UpgradeAbandoned',
        'ClassificationOverridden','PromptGenerated',
        'BriefCreated','BriefUpdated','BriefAbandoned','BriefCompleted',
        'BriefStepSkipped','BriefQuestionSkipped','BriefTrackAbandoned',
        'TokenRefreshed')),
    CONSTRAINT ck_al_entity_type CHECK (entity_type IN (
        'Prompt','PromptVersion','ComplianceCheck','User',
        'UpgradeProposal','Brief'))
);

-- ── briefs ────────────────────────────────────────────────────────────────────
CREATE TABLE briefs (
    brief_id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    title                 TEXT,
    status                TEXT NOT NULL DEFAULT 'In Progress',
    quality_score         INTEGER NOT NULL DEFAULT 0,
    step_progress         INTEGER NOT NULL DEFAULT 1,
    client_name           TEXT,
    business_owner_name   TEXT,
    business_owner_role   TEXT,
    brief_builder_id      TEXT NOT NULL REFERENCES users(user_id),
    interviewer_id        TEXT REFERENCES users(user_id),
    step_answers          TEXT NOT NULL DEFAULT '{}',
    selected_guardrails   TEXT NOT NULL DEFAULT '[]',
    restructured_brief    TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    submitted_at          TEXT,
    resulting_prompt_id   TEXT REFERENCES prompts(prompt_id),

    CONSTRAINT ck_briefs_status
        CHECK (status IN ('In Progress','Complete','Abandoned','Archived'))
);

-- ── prompt_components ─────────────────────────────────────────────────────────
CREATE TABLE prompt_components (
    component_id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    code                  TEXT UNIQUE NOT NULL,
    category              TEXT NOT NULL,
    name                  TEXT NOT NULL,
    description           TEXT NOT NULL,
    component_text        TEXT NOT NULL,
    example_output        TEXT,
    applicable_dimensions TEXT NOT NULL DEFAULT '[]',
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order            INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT ck_pc_category
        CHECK (category IN (
            'InputHandling','OutputFormat','RegulatoryGuardrail','Behavioural'))
);

-- ── prompt_templates ──────────────────────────────────────────────────────────
CREATE TABLE prompt_templates (
    template_id                TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
    code                       TEXT UNIQUE NOT NULL,
    name                       TEXT NOT NULL,
    description                TEXT NOT NULL,
    use_case                   TEXT,
    prompt_type                TEXT NOT NULL,
    risk_tier                  TEXT NOT NULL DEFAULT 'Limited',
    input_type                 TEXT,
    output_type                TEXT,
    component_codes            TEXT NOT NULL DEFAULT '[]',
    prompt_text                TEXT,
    output_example             TEXT,
    gold_standard_grade        TEXT,
    applicable_to_client_types TEXT,
    is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order                 INTEGER NOT NULL DEFAULT 0
);

-- ══════════════════════════════════════════════════════════════════════════════
-- DEFERRED FOREIGN KEYS (circular references)
-- ══════════════════════════════════════════════════════════════════════════════

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

-- ══════════════════════════════════════════════════════════════════════════════
-- INDEXES
-- ══════════════════════════════════════════════════════════════════════════════

-- Only one active version per prompt
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_version_per_prompt
    ON prompt_versions (prompt_id)
    WHERE is_active = TRUE;

-- ══════════════════════════════════════════════════════════════════════════════
-- TRIGGERS
-- ══════════════════════════════════════════════════════════════════════════════

-- ── AuditLog — set timestamp on insert ──────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_set_audit_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.timestamp := NOW()::TEXT;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_log_timestamp
    BEFORE INSERT ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_set_audit_timestamp();

-- ── AuditLog — prevent deletion ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_prevent_audit_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AuditLog records cannot be deleted';
END;
$$;

CREATE TRIGGER trg_prevent_audit_log_delete
    BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_delete();

-- ── AuditLog — prevent core field updates ───────────────────────────────────
-- resolved / resolved_at / resolved_by are intentionally excluded so
-- the review-queue resolve endpoint can mark items as resolved.
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

-- ── PromptVersion — prevent deletion ─────────────────────────────────────────
CREATE OR REPLACE FUNCTION fn_prevent_pv_delete()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'PromptVersion records cannot be deleted';
END;
$$;

CREATE TRIGGER trg_prevent_prompt_version_delete
    BEFORE DELETE ON prompt_versions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_pv_delete();

-- ── PromptVersion — prevent immutable content field updates ──────────────────
-- Operational fields (cache_valid, compliance_check_id, is_active,
-- approved_by, approved_at, defects_found, corrections_made,
-- regulatory_scores, injection_scan_result, upgrade_proposal_id)
-- are intentionally excluded from this guard.
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

-- ── ScoringDimension update — invalidate compliance cache ────────────────────
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
