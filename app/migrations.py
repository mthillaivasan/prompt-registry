"""
Ensure all tables and columns exist in the connected database.
Runs on startup after Base.metadata.create_all().
Uses IF NOT EXISTS for safety — idempotent.
"""

from sqlalchemy import text


def run_migrations(engine) -> None:
    """Add any columns/tables that may be missing in an existing Postgres database."""
    is_sqlite = "sqlite" in str(engine.url)

    with engine.connect() as conn:
        # scoring_dimensions.tier and tier2_trigger
        _add_column(conn, "scoring_dimensions", "tier", "INTEGER DEFAULT 3", is_sqlite)
        _add_column(conn, "scoring_dimensions", "tier2_trigger", "TEXT", is_sqlite)

        # briefs table
        _create_table_if_not_exists(conn, "briefs", """
            brief_id VARCHAR(36) PRIMARY KEY,
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

        # prompt_components table
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

        # prompt_templates table
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

        # prompt_versions.upgrade_proposal_id (may be missing)
        _add_column(conn, "prompt_versions", "upgrade_proposal_id", "VARCHAR(36)", is_sqlite)

        conn.commit()
    print("Migration check complete")


def _add_column(conn, table: str, column: str, col_type: str, is_sqlite: bool) -> None:
    try:
        if is_sqlite:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        else:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
    except Exception:
        pass  # Column already exists


def _create_table_if_not_exists(conn, table: str, columns: str, is_sqlite: bool) -> None:
    try:
        conn.execute(text(f"CREATE TABLE IF NOT EXISTS {table} ({columns})"))
    except Exception as e:
        print(f"Warning: Could not create table {table}: {e}")
