"""
Ensure all tables and columns exist in the connected database.
Runs on startup after Base.metadata.create_all().

Fails fast on error — if a migration step fails, the app should not
start with a silently broken schema. The caller (main.py lifespan)
is responsible for deciding whether to abort or continue.
"""

from sqlalchemy import text


def run_migrations(engine) -> None:
    """Add any columns/tables that may be missing in an existing database.

    Raises on failure so the caller knows exactly which step broke.
    """
    is_sqlite = "sqlite" in str(engine.url)

    with engine.connect() as conn:
        _add_column(conn, "scoring_dimensions", "tier", "INTEGER NOT NULL DEFAULT 3", is_sqlite)
        _add_column(conn, "scoring_dimensions", "tier2_trigger", "TEXT", is_sqlite)
        _add_column(conn, "scoring_dimensions", "instructional_text", "TEXT", is_sqlite)
        _add_column(conn, "scoring_dimensions", "updated_at", "VARCHAR", is_sqlite)
        _add_column(conn, "scoring_dimensions", "updated_by", "VARCHAR(36)", is_sqlite)
        # Drop 3 Item 3: three-category classification for generator filtering.
        _add_column(conn, "scoring_dimensions", "content_type", "VARCHAR", is_sqlite)

        _create_table_if_not_exists(conn, "briefs", """
            brief_id VARCHAR(36) PRIMARY KEY,
            title VARCHAR,
            status VARCHAR NOT NULL DEFAULT 'In Progress',
            quality_score INTEGER NOT NULL DEFAULT 0,
            step_progress INTEGER NOT NULL DEFAULT 1,
            client_name VARCHAR,
            business_owner_name VARCHAR,
            business_owner_role VARCHAR,
            brief_builder_id VARCHAR(36) NOT NULL,
            interviewer_id VARCHAR(36),
            step_answers TEXT NOT NULL DEFAULT '{}',
            selected_guardrails TEXT NOT NULL DEFAULT '[]',
            restructured_brief TEXT,
            created_at VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL,
            submitted_at VARCHAR,
            resulting_prompt_id VARCHAR(36)
        """, is_sqlite)
        _add_column(conn, "briefs", "title", "VARCHAR", is_sqlite)

        _create_table_if_not_exists(conn, "prompt_components", """
            component_id VARCHAR(36) PRIMARY KEY,
            code VARCHAR UNIQUE NOT NULL,
            category VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            description TEXT NOT NULL,
            component_text TEXT NOT NULL,
            example_output TEXT,
            applicable_dimensions TEXT NOT NULL DEFAULT '[]',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        """, is_sqlite)

        _create_table_if_not_exists(conn, "prompt_templates", """
            template_id VARCHAR(36) PRIMARY KEY,
            code VARCHAR UNIQUE NOT NULL,
            name VARCHAR NOT NULL,
            description TEXT NOT NULL,
            use_case TEXT,
            prompt_type VARCHAR NOT NULL,
            risk_tier VARCHAR NOT NULL DEFAULT 'Limited',
            input_type VARCHAR,
            output_type VARCHAR,
            component_codes TEXT NOT NULL DEFAULT '[]',
            prompt_text TEXT,
            output_example TEXT,
            gold_standard_grade VARCHAR,
            applicable_to_client_types TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0
        """, is_sqlite)

        _create_table_if_not_exists(conn, "prompt_library", """
            library_id VARCHAR(36) PRIMARY KEY,
            title VARCHAR UNIQUE NOT NULL,
            full_text TEXT NOT NULL,
            summary TEXT,
            prompt_type VARCHAR NOT NULL,
            input_type VARCHAR,
            output_type VARCHAR,
            domain VARCHAR NOT NULL DEFAULT 'general',
            source_provenance TEXT,
            topic_coverage TEXT NOT NULL DEFAULT '[]',
            classification_notes TEXT,
            created_at VARCHAR NOT NULL,
            updated_at VARCHAR NOT NULL
        """, is_sqlite)

        _add_column(conn, "prompt_versions", "upgrade_proposal_id", "VARCHAR(36)", is_sqlite)

        # Drop 1: token count and estimated cost per invocation (see services/pricing.py).
        _add_column(conn, "prompt_versions", "token_count", "INTEGER", is_sqlite)
        _add_column(conn, "prompt_versions", "estimated_cost_usd", "VARCHAR", is_sqlite)

        # Transitional split: deployment_target → ai_platform + output_destination.
        # Both nullable; existing rows keep deployment_target, new writes dual-populate.
        _add_column(conn, "prompts", "ai_platform", "VARCHAR", is_sqlite)
        _add_column(conn, "prompts", "output_destination", "VARCHAR", is_sqlite)

        # Phase B2: expand audit_log action CHECK constraint to admit 'BriefDeleted'.
        # SQLite can't ALTER a CHECK constraint — fresh test DBs pick up the new
        # constraint from models.py via create_all. Postgres runtime needs the
        # drop+recreate below to accept the new action value.
        if not is_sqlite:
            conn.execute(text("ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS ck_al_action"))
            conn.execute(text(
                "ALTER TABLE audit_log ADD CONSTRAINT ck_al_action CHECK (action IN ("
                "'Created','Edited','Activated','Retired','ComplianceChecked',"
                "'Approved','DefectLogged','Corrected','InjectionDetected',"
                "'ValidationFailed','Accessed','PromptImported','UpgradeProposed',"
                "'UpgradeResponseRecorded','UpgradeApplied','UpgradeAbandoned',"
                "'ClassificationOverridden','PromptGenerated',"
                "'BriefCreated','BriefUpdated','BriefDeleted','BriefAbandoned','BriefCompleted',"
                "'BriefStepSkipped','BriefQuestionSkipped','BriefTrackAbandoned',"
                "'TokenRefreshed'))"
            ))

        conn.commit()
    print("Migration check complete")


def _add_column(conn, table: str, column: str, col_type: str, is_sqlite: bool) -> None:
    """Add a column if it does not already exist.

    On Postgres, IF NOT EXISTS handles idempotency natively.
    On SQLite, IF NOT EXISTS is not supported for ALTER TABLE, so we
    check the pragma first and skip if the column is already present.
    """
    if is_sqlite:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        existing = {row[1] for row in rows}
        if column in existing:
            return
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        print(f"  Added column {table}.{column}")
    else:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
        print(f"  Ensured column {table}.{column}")


def _create_table_if_not_exists(conn, table: str, columns: str, is_sqlite: bool) -> None:
    """Create a table if it does not already exist. Raises on failure."""
    conn.execute(text(f"CREATE TABLE IF NOT EXISTS {table} ({columns})"))
    print(f"  Ensured table {table}")
