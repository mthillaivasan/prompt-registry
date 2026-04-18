#!/usr/bin/env python3
"""
Schema drift detection tool.

Connects to the configured DATABASE_URL and verifies that the live
database matches the SQLAlchemy models in app/models.py.

Checks:
  1. Every model has a corresponding table
  2. Every column in each model exists with the correct type
  3. Every named CHECK constraint in the models exists in the database
  4. Critical Postgres triggers exist (Postgres only)

Usage:
  DATABASE_URL=postgresql://... python scripts/verify_schema.py
  DATABASE_URL=sqlite:///./data/prompt_registry.db python scripts/verify_schema.py

Exit codes:
  0 — all checks pass
  1 — one or more checks failed (diff report printed)
  2 — could not connect to database
"""

import os
import sys

# Ensure the project root is on the path so app.* imports work.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.models import (  # noqa: F401 — imports register all models with Base
    AuditLog,
    Brief,
    ComplianceCheck,
    ComplianceCheckJob,
    InjectionPattern,
    Prompt,
    PromptComponent,
    PromptTemplate,
    PromptVersion,
    ScoringDimension,
    UpgradeProposal,
    User,
)

# ── SQLAlchemy type → expected DB type mapping ─────────────────────────────────
# SQLAlchemy Column types map to different DDL strings depending on backend.
# We normalise both sides to a canonical form for comparison.

_SA_TYPE_MAP = {
    "VARCHAR": "TEXT",
    "BOOLEAN": "BOOLEAN",
    "INTEGER": "INTEGER",
    "TEXT": "TEXT",
}


def _normalise_sa_type(sa_type_str: str) -> str:
    """Normalise a SQLAlchemy column type string for comparison."""
    upper = sa_type_str.upper()
    # VARCHAR(N) → TEXT
    if upper.startswith("VARCHAR"):
        return "TEXT"
    return _SA_TYPE_MAP.get(upper, upper)


def _normalise_db_type(db_type_str: str) -> str:
    """Normalise a database column type string for comparison."""
    upper = (db_type_str or "").upper().strip()
    if upper.startswith("VARCHAR") or upper.startswith("CHARACTER VARYING"):
        return "TEXT"
    if upper in ("BOOL",):
        return "BOOLEAN"
    if upper in ("INT", "BIGINT", "SMALLINT", "INT4", "INT8", "INT2"):
        return "INTEGER"
    return upper


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "sqlite:///./data/prompt_registry.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    is_postgres = "postgresql" in db_url
    is_sqlite = "sqlite" in db_url

    try:
        if is_sqlite:
            engine = create_engine(db_url, connect_args={"check_same_thread": False})
        else:
            engine = create_engine(db_url)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"FATAL: Cannot connect to database: {e}", file=sys.stderr)
        return 2

    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())

    errors: list[str] = []
    warnings: list[str] = []

    # ── Check 1: Every model has a table ───────────────────────────────────────
    print("=== Check 1: Table existence ===")
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table_name = model.__tablename__
        if table_name in db_tables:
            print(f"  OK  {table_name}")
        else:
            errors.append(f"MISSING TABLE: {table_name} (model {model.__name__})")
            print(f"  FAIL  {table_name} — table does not exist")

    # ── Check 2: Every column exists with correct type ─────────────────────────
    print("\n=== Check 2: Column existence and types ===")
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table_name = model.__tablename__
        if table_name not in db_tables:
            continue  # Already reported in Check 1

        db_columns = {col["name"]: col for col in inspector.get_columns(table_name)}

        for sa_col in mapper.columns:
            col_name = sa_col.name
            expected_type = _normalise_sa_type(str(sa_col.type))

            if col_name not in db_columns:
                errors.append(
                    f"MISSING COLUMN: {table_name}.{col_name} "
                    f"(expected {expected_type})"
                )
                print(f"  FAIL  {table_name}.{col_name} — column does not exist")
                continue

            actual_type = _normalise_db_type(str(db_columns[col_name]["type"]))
            if expected_type != actual_type:
                errors.append(
                    f"TYPE MISMATCH: {table_name}.{col_name} — "
                    f"expected {expected_type}, got {actual_type}"
                )
                print(
                    f"  FAIL  {table_name}.{col_name} — "
                    f"expected {expected_type}, got {actual_type}"
                )
            else:
                print(f"  OK  {table_name}.{col_name} ({actual_type})")

    # ── Check 3: Named CHECK constraints exist ─────────────────────────────────
    print("\n=== Check 3: CHECK constraints ===")
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table_name = model.__tablename__
        if table_name not in db_tables:
            continue

        # Get CHECK constraints from the database
        db_checks = set()
        try:
            for ck in inspector.get_check_constraints(table_name):
                db_checks.add(ck["name"])
        except NotImplementedError:
            # Some backends don't support get_check_constraints
            warnings.append(
                f"SKIP: Cannot inspect CHECK constraints on {table_name} "
                f"(backend does not support it)"
            )
            print(f"  SKIP  {table_name} — backend does not support CHECK inspection")
            continue

        # Get expected CHECK constraints from the model's __table_args__
        table_args = getattr(model, "__table_args__", None)
        if not table_args:
            continue

        if isinstance(table_args, tuple):
            constraints = table_args
        elif isinstance(table_args, dict):
            constraints = ()
        else:
            constraints = ()

        for arg in constraints:
            if hasattr(arg, "name") and arg.name and arg.name.startswith("ck_"):
                if arg.name in db_checks:
                    print(f"  OK  {table_name}.{arg.name}")
                else:
                    errors.append(
                        f"MISSING CONSTRAINT: {table_name}.{arg.name}"
                    )
                    print(f"  FAIL  {table_name}.{arg.name} — constraint not found")

    # ── Check 4: Critical Postgres triggers ────────────────────────────────────
    if is_postgres:
        print("\n=== Check 4: Postgres triggers ===")
        expected_triggers = {
            "prompt_versions": [
                "trg_prevent_prompt_version_delete",
                "trg_prevent_prompt_version_content_update",
            ],
            "audit_log": [
                "trg_audit_log_timestamp",
                "trg_prevent_audit_log_delete",
                "trg_prevent_audit_log_core_update",
            ],
            "scoring_dimensions": [
                "trg_invalidate_cache_on_dimension_update",
            ],
        }

        with engine.connect() as conn:
            for table, trigger_names in expected_triggers.items():
                result = conn.execute(text(
                    "SELECT trigger_name FROM information_schema.triggers "
                    "WHERE event_object_table = :table "
                    "AND trigger_schema = 'public'",
                ), {"table": table})
                db_trigger_names = {row[0] for row in result}

                for tname in trigger_names:
                    if tname in db_trigger_names:
                        print(f"  OK  {table}.{tname}")
                    else:
                        errors.append(
                            f"MISSING TRIGGER: {table}.{tname}"
                        )
                        print(f"  FAIL  {table}.{tname} — trigger not found")
    else:
        print("\n=== Check 4: Triggers (SQLite — skipped, verified at runtime) ===")
        print("  SKIP  SQLite triggers are applied on every startup via triggers.py")

    # ── Summary ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED: {len(errors)} error(s) found\n")
        for e in errors:
            print(f"  - {e}")
        if warnings:
            print(f"\n  Plus {len(warnings)} warning(s):")
            for w in warnings:
                print(f"  - {w}")
        return 1
    else:
        msg = "ALL CHECKS PASSED"
        if warnings:
            msg += f" ({len(warnings)} warning(s))"
        print(msg)
        if warnings:
            for w in warnings:
                print(f"  - {w}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
