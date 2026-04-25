"""
Phase 2 seed loader.

Loads configuration from seed/*.yml into the new dimensions / standards /
phases / gates / phase_weights / form_fields tables. Idempotent: re-runs
update existing rows by `code` rather than inserting duplicates.

Called from app.main after run_seed() so that when a fresh database is
brought up, both the legacy ScoringDimension catalogue and the new
Dimension catalogue are populated. The two coexist during the Block 9
engine transition.

This module never references dimension codes by name in code. It loads
whatever YAML it is given. A test that wants synthetic dimensions can
point this at a fixture file.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Dimension,
    FormField,
    Gate,
    GateMustPassDimension,
    Phase,
    PhaseWeight,
    Standard,
)


SEED_DIR = Path(__file__).resolve().parent.parent / "seed"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_yaml(name: str) -> dict:
    path = SEED_DIR / name
    if not path.exists():
        return {}
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _upsert_standards(db: Session, data: dict) -> dict[str, str]:
    """Returns map of standard_code -> standard_id."""
    code_to_id: dict[str, str] = {}
    for entry in data.get("standards", []):
        code = entry["standard_code"]
        existing = db.query(Standard).filter_by(standard_code=code).one_or_none()
        if existing is None:
            row = Standard(
                standard_code=code,
                title=entry["title"],
                version=entry["version"],
                publisher=entry["publisher"],
                url=entry.get("url"),
                notes=entry.get("notes"),
                is_active=entry.get("is_active", True),
            )
            db.add(row)
            db.flush()
            code_to_id[code] = row.standard_id
        else:
            existing.title = entry["title"]
            existing.version = entry["version"]
            existing.publisher = entry["publisher"]
            existing.url = entry.get("url")
            existing.notes = entry.get("notes")
            existing.is_active = entry.get("is_active", True)
            existing.updated_at = _utcnow()
            code_to_id[code] = existing.standard_id
    return code_to_id


def _upsert_phases(db: Session, data: dict) -> dict[str, str]:
    code_to_id: dict[str, str] = {}
    for entry in data.get("phases", []):
        code = entry["code"]
        thresholds = entry.get("grade_thresholds", {})
        existing = db.query(Phase).filter_by(code=code).one_or_none()
        if existing is None:
            row = Phase(
                code=code,
                title=entry["title"],
                purpose=entry["purpose"],
                scoring_input=entry["scoring_input"],
                sort_order=entry.get("sort_order", 0),
                pass_threshold=str(thresholds.get("pass", "4.0")),
                pass_with_warnings_threshold=str(thresholds.get("pass_with_warnings", "3.0")),
            )
            db.add(row)
            db.flush()
            code_to_id[code] = row.phase_id
        else:
            existing.title = entry["title"]
            existing.purpose = entry["purpose"]
            existing.scoring_input = entry["scoring_input"]
            existing.sort_order = entry.get("sort_order", 0)
            existing.pass_threshold = str(thresholds.get("pass", "4.0"))
            existing.pass_with_warnings_threshold = str(thresholds.get("pass_with_warnings", "3.0"))
            code_to_id[code] = existing.phase_id
    return code_to_id


def _upsert_phase_weights(
    db: Session,
    data: dict,
    phase_codes: dict[str, str],
    standard_codes: dict[str, str],
) -> None:
    weights = data.get("phase_weights", {})
    for phase_code, by_standard in weights.items():
        phase_id = phase_codes.get(phase_code)
        if phase_id is None:
            continue
        for standard_code, weight in by_standard.items():
            standard_id = standard_codes.get(standard_code)
            if standard_id is None:
                continue
            existing = (
                db.query(PhaseWeight)
                .filter_by(phase_id=phase_id, standard_id=standard_id)
                .one_or_none()
            )
            if existing is None:
                db.add(
                    PhaseWeight(
                        phase_id=phase_id,
                        standard_id=standard_id,
                        weight=str(weight),
                    )
                )
            else:
                existing.weight = str(weight)


def _upsert_dimensions(
    db: Session,
    data: dict,
    phase_codes: dict[str, str],
    standard_codes: dict[str, str],
) -> dict[str, str]:
    """Returns map of dimension code -> dimension_id."""
    code_to_id: dict[str, str] = {}
    for entry in data.get("dimensions", []):
        code = entry["code"]
        phase_id = phase_codes.get(entry["phase"])
        standard_id = standard_codes.get(entry["standard_code"])
        if phase_id is None or standard_id is None:
            # Skip dimensions whose phase or standard wasn't loaded.
            # The engine treats missing rows as inapplicable.
            continue

        rubric = entry.get("scoring_rubric", {})
        applicability = entry.get("applicability", {"always": True})

        fields = dict(
            title=entry["title"],
            phase_id=phase_id,
            standard_id=standard_id,
            clause=entry.get("clause"),
            sort_order=entry.get("sort_order", 0),
            blocking_threshold=entry.get("blocking_threshold", 2),
            is_mandatory=entry.get("is_mandatory", False),
            scoring_type=entry.get("scoring_type", "Advisory"),
            content_type=entry.get("content_type"),
            applicability=json.dumps(applicability),
            score_5_criteria=rubric.get("score_5", ""),
            score_3_criteria=rubric.get("score_3", ""),
            score_1_criteria=rubric.get("score_1", ""),
            instructional_text=entry.get("instructional_text"),
            is_active=entry.get("is_active", True),
        )

        existing = db.query(Dimension).filter_by(code=code).one_or_none()
        if existing is None:
            row = Dimension(code=code, **fields)
            db.add(row)
            db.flush()
            code_to_id[code] = row.dimension_id
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            existing.updated_at = _utcnow()
            code_to_id[code] = existing.dimension_id
    return code_to_id


def _upsert_gates(
    db: Session,
    data: dict,
    phase_codes: dict[str, str],
    dimension_codes: dict[str, str],
) -> None:
    for entry in data.get("gates", []):
        code = entry["code"]
        phase_id = phase_codes.get(entry["phase"])
        if phase_id is None:
            continue
        existing = db.query(Gate).filter_by(code=code).one_or_none()
        if existing is None:
            gate = Gate(
                code=code,
                title=entry["title"],
                from_phase_id=phase_id,
                min_grade=str(entry.get("min_grade", "3.0")),
                approver_role=entry.get("approver_role", "Checker"),
                rationale_required=entry.get("rationale_required", True),
            )
            db.add(gate)
            db.flush()
        else:
            existing.title = entry["title"]
            existing.from_phase_id = phase_id
            existing.min_grade = str(entry.get("min_grade", "3.0"))
            existing.approver_role = entry.get("approver_role", "Checker")
            existing.rationale_required = entry.get("rationale_required", True)
            gate = existing

        # Replace must-pass-dimensions associations to match config.
        db.query(GateMustPassDimension).filter_by(gate_id=gate.gate_id).delete()
        for dim_code in entry.get("must_pass_dimensions", []):
            dim_id = dimension_codes.get(dim_code)
            if dim_id is None:
                continue
            db.add(GateMustPassDimension(gate_id=gate.gate_id, dimension_id=dim_id))


def _upsert_form_fields(db: Session, data: dict) -> None:
    """Form fields seeding. Optional — not all phases ship with form_fields.yml."""
    for entry in data.get("form_fields", []):
        form_code = entry["form_code"]
        field_code = entry["field_code"]
        existing = (
            db.query(FormField)
            .filter_by(form_code=form_code, field_code=field_code)
            .one_or_none()
        )
        fields = dict(
            label=entry["label"],
            help_text=entry.get("help_text"),
            field_type=entry["field_type"],
            options=json.dumps(entry["options"]) if entry.get("options") is not None else None,
            validation=json.dumps(entry["validation"]) if entry.get("validation") is not None else None,
            sort_order=entry.get("sort_order", 0),
            is_active=entry.get("is_active", True),
        )
        if existing is None:
            db.add(FormField(form_code=form_code, field_code=field_code, **fields))
        else:
            for k, v in fields.items():
                setattr(existing, k, v)


def run_phase2_seed(db: Session | None = None) -> None:
    """Idempotent seed loader for the Phase 2 configuration tables.

    Safe to call on every startup. If the seed YAMLs are absent (e.g. an
    older deployment), this is a no-op — the loader returns silently.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        standards_data = _load_yaml("standards.yml")
        phases_data = _load_yaml("phases.yml")
        dimensions_data = _load_yaml("dimensions.yml")
        gates_data = _load_yaml("gates.yml")
        form_fields_data = _load_yaml("form_fields.yml")

        if not (standards_data or phases_data or dimensions_data or gates_data):
            print("Phase 2 seed: no seed/*.yml files present, skipping.")
            return

        standard_codes = _upsert_standards(db, standards_data)
        phase_codes = _upsert_phases(db, phases_data)
        _upsert_phase_weights(db, standards_data, phase_codes, standard_codes)
        dimension_codes = _upsert_dimensions(db, dimensions_data, phase_codes, standard_codes)
        _upsert_gates(db, gates_data, phase_codes, dimension_codes)
        _upsert_form_fields(db, form_fields_data)

        db.commit()
        print(
            f"Phase 2 seed: standards={len(standard_codes)} "
            f"phases={len(phase_codes)} dimensions={len(dimension_codes)}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        if own_session:
            db.close()
