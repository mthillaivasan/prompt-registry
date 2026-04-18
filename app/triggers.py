"""
Database-level triggers and indexes.
Applied once after Base.metadata.create_all() on startup.

Supports both SQLite and Postgres backends. The trigger logic is
identical — only the syntax differs. Raises on failure so the
caller knows if immutability protections are missing.
"""

from sqlalchemy import text

# ══════════════════════════════════════════════════════════════════════════════
# SQLite triggers
# ══════════════════════════════════════════════════════════════════════════════

_SQLITE_TRIGGERS = [
    # ── PromptVersion: prevent deletion ──────────────────────────────────────
    """
    CREATE TRIGGER IF NOT EXISTS prevent_prompt_version_delete
    BEFORE DELETE ON prompt_versions
    BEGIN
        SELECT RAISE(ABORT, 'PromptVersion records cannot be deleted');
    END
    """,

    # ── PromptVersion: prevent updates to immutable content fields ───────────
    # Operational fields (cache_valid, compliance_check_id, is_active,
    # approved_by, approved_at, defects_found, corrections_made,
    # regulatory_scores, injection_scan_result, upgrade_proposal_id)
    # are intentionally excluded from this guard.
    """
    CREATE TRIGGER IF NOT EXISTS prevent_prompt_version_content_update
    BEFORE UPDATE ON prompt_versions
    WHEN OLD.prompt_text        != NEW.prompt_text
      OR OLD.version_number     != NEW.version_number
      OR OLD.prompt_id          != NEW.prompt_id
      OR OLD.created_by         != NEW.created_by
      OR OLD.created_at         != NEW.created_at
      OR (OLD.previous_version_id IS NULL) != (NEW.previous_version_id IS NULL)
      OR (OLD.previous_version_id IS NOT NULL
          AND NEW.previous_version_id IS NOT NULL
          AND OLD.previous_version_id != NEW.previous_version_id)
    BEGIN
        SELECT RAISE(ABORT, 'PromptVersion content fields are immutable');
    END
    """,

    # ── AuditLog: prevent deletion ───────────────────────────────────────────
    """
    CREATE TRIGGER IF NOT EXISTS prevent_audit_log_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'AuditLog records cannot be deleted');
    END
    """,

    # ── AuditLog: prevent updates to core fields ─────────────────────────────
    # resolved / resolved_at / resolved_by are intentionally excluded so
    # the review-queue resolve endpoint can mark items as resolved.
    """
    CREATE TRIGGER IF NOT EXISTS prevent_audit_log_core_update
    BEFORE UPDATE ON audit_log
    WHEN OLD.log_id       != NEW.log_id
      OR OLD.timestamp    != NEW.timestamp
      OR OLD.action       != NEW.action
      OR OLD.entity_type  != NEW.entity_type
      OR OLD.entity_id    != NEW.entity_id
      OR (OLD.user_id IS NULL) != (NEW.user_id IS NULL)
      OR (OLD.user_id IS NOT NULL AND NEW.user_id IS NOT NULL
          AND OLD.user_id != NEW.user_id)
      OR (OLD.detail IS NULL) != (NEW.detail IS NULL)
      OR (OLD.detail IS NOT NULL AND NEW.detail IS NOT NULL
          AND OLD.detail != NEW.detail)
    BEGIN
        SELECT RAISE(ABORT, 'AuditLog core fields are immutable');
    END
    """,

    # ── ScoringDimension: invalidate cache on any dimension update ───────────
    """
    CREATE TRIGGER IF NOT EXISTS invalidate_cache_on_dimension_update
    AFTER UPDATE ON scoring_dimensions
    BEGIN
        UPDATE prompt_versions
        SET cache_valid = 0
        WHERE compliance_check_id IS NOT NULL;
    END
    """,
]

# ══════════════════════════════════════════════════════════════════════════════
# Postgres triggers — CREATE OR REPLACE is idempotent for functions;
# triggers use DROP IF EXISTS + CREATE to allow re-running safely.
# ══════════════════════════════════════════════════════════════════════════════

_POSTGRES_TRIGGERS = [
    # ── PromptVersion: prevent deletion ──────────────────────────────────────
    """
    CREATE OR REPLACE FUNCTION fn_prevent_pv_delete()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'PromptVersion records cannot be deleted';
    END;
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_prevent_prompt_version_delete ON prompt_versions
    """,
    """
    CREATE TRIGGER trg_prevent_prompt_version_delete
        BEFORE DELETE ON prompt_versions
        FOR EACH ROW EXECUTE FUNCTION fn_prevent_pv_delete()
    """,

    # ── PromptVersion: prevent immutable content field updates ────────────────
    """
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
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_prevent_prompt_version_content_update ON prompt_versions
    """,
    """
    CREATE TRIGGER trg_prevent_prompt_version_content_update
        BEFORE UPDATE ON prompt_versions
        FOR EACH ROW EXECUTE FUNCTION fn_prevent_pv_content_update()
    """,

    # ── AuditLog: set timestamp on insert ────────────────────────────────────
    """
    CREATE OR REPLACE FUNCTION fn_set_audit_timestamp()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        NEW.timestamp := NOW()::TEXT;
        RETURN NEW;
    END;
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_audit_log_timestamp ON audit_log
    """,
    """
    CREATE TRIGGER trg_audit_log_timestamp
        BEFORE INSERT ON audit_log
        FOR EACH ROW EXECUTE FUNCTION fn_set_audit_timestamp()
    """,

    # ── AuditLog: prevent deletion ───────────────────────────────────────────
    """
    CREATE OR REPLACE FUNCTION fn_prevent_audit_delete()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'AuditLog records cannot be deleted';
    END;
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_prevent_audit_log_delete ON audit_log
    """,
    """
    CREATE TRIGGER trg_prevent_audit_log_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_delete()
    """,

    # ── AuditLog: prevent core field updates ─────────────────────────────────
    # resolved / resolved_at / resolved_by are intentionally excluded.
    """
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
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_prevent_audit_log_core_update ON audit_log
    """,
    """
    CREATE TRIGGER trg_prevent_audit_log_core_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION fn_prevent_audit_core_update()
    """,

    # ── ScoringDimension update — invalidate compliance cache ────────────────
    """
    CREATE OR REPLACE FUNCTION fn_invalidate_cache_on_dimension_update()
    RETURNS TRIGGER LANGUAGE plpgsql AS $$
    BEGIN
        UPDATE prompt_versions
        SET cache_valid = FALSE
        WHERE compliance_check_id IS NOT NULL;
        RETURN NEW;
    END;
    $$
    """,
    """
    DROP TRIGGER IF EXISTS trg_invalidate_cache_on_dimension_update ON scoring_dimensions
    """,
    """
    CREATE TRIGGER trg_invalidate_cache_on_dimension_update
        AFTER UPDATE ON scoring_dimensions
        FOR EACH ROW EXECUTE FUNCTION fn_invalidate_cache_on_dimension_update()
    """,
]

# ══════════════════════════════════════════════════════════════════════════════
# Indexes — syntax works on both SQLite and Postgres
# ══════════════════════════════════════════════════════════════════════════════

_SQLITE_INDEXES = [
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_version_per_prompt
    ON prompt_versions (prompt_id)
    WHERE is_active = 1
    """,
]

_POSTGRES_INDEXES = [
    # idx_one_active_version_per_prompt is defined in 001_initial.sql
    # (the authoritative Postgres schema). Not duplicated here.
]


def create_triggers_and_indexes(engine) -> None:
    """Apply all triggers and indexes for the current backend.

    Raises on failure — if a trigger cannot be created, the app must
    not start without immutability protections.
    """
    is_sqlite = "sqlite" in str(engine.url)

    if is_sqlite:
        stmts = _SQLITE_TRIGGERS + _SQLITE_INDEXES
    else:
        stmts = _POSTGRES_TRIGGERS + _POSTGRES_INDEXES

    with engine.connect() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))
        conn.commit()

    backend = "SQLite" if is_sqlite else "Postgres"
    print(f"Triggers and indexes applied ({backend})")
