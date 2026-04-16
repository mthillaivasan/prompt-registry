"""
Database-level triggers and indexes.
Applied once after Base.metadata.create_all() on startup.

SQLite trigger syntax is used here. The equivalent Postgres triggers are
documented in migrations/001_initial.sql.
"""

from sqlalchemy import text

_TRIGGERS = [
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
    # Sets cache_valid = false on every PromptVersion that has already had
    # a compliance check run (compliance_check_id IS NOT NULL).
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

_INDEXES = [
    # Partial unique index: only one active version per prompt.
    # Postgres-compatible syntax (SQLite supports WHERE on CREATE UNIQUE INDEX).
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_version_per_prompt
    ON prompt_versions (prompt_id)
    WHERE is_active = 1
    """,
]


def create_triggers_and_indexes(engine) -> None:
    with engine.connect() as conn:
        for stmt in _TRIGGERS + _INDEXES:
            conn.execute(text(stmt))
        conn.commit()
