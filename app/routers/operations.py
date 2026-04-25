"""
Operation-phase router — Block 18.

Endpoints expose the Operation lifecycle: list / get records, append
incidents, run cadence-driven compliance, retire, return-to-active.

Auto-creation of an operation_record happens at the deployment gate's
Approved branch (see app/routers/deployments.py); this router does not
expose a public POST /operation endpoint.

Configuration-first: cadence comes from the deployment form response
or a phase default, never a code constant. Severity threshold for
auto-Under-Review lives in services.operation_lifecycle and reads the
incident's severity field — no per-record code.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    AuditLog,
    DeploymentRecord,
    Dimension,
    OperationRecord,
    Standard,
    User,
)
from services import operation_lifecycle

router = APIRouter(tags=["operations"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# Same role hierarchy as the deployment gate. Single source of truth would be
# nice (PHASE3); for now duplicated here to keep router-level imports simple.
_ROLE_RANK = {"Maker": 1, "Checker": 2, "Admin": 3}


def _role_satisfies(actual: str, required: str) -> bool:
    return _ROLE_RANK.get(actual, 0) >= _ROLE_RANK.get(required, 999)


def _serialise_record(r: OperationRecord) -> dict:
    incidents = json.loads(r.incidents_json) if r.incidents_json else []
    return {
        "operation_id": r.operation_id,
        "deployment_id": r.deployment_id,
        "state": r.state,
        "next_review_date": r.next_review_date,
        "review_cadence_days": r.review_cadence_days,
        "incidents": incidents,
        "incident_count": len(incidents),
        "retired_at": r.retired_at,
        "retired_reason": r.retired_reason,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _serialise_run(run, db: Session | None = None) -> dict:
    scores = json.loads(run.scores_json) if run.scores_json else []
    flags = json.loads(run.flags_json) if run.flags_json else []
    composite = float(run.composite_grade) if run.composite_grade is not None else None
    if db is not None and scores:
        dim_ids = [s["dimension_id"] for s in scores if s.get("dimension_id")]
        dims = {d.dimension_id: d for d in db.query(Dimension).filter(Dimension.dimension_id.in_(dim_ids)).all()}
        std_ids = {d.standard_id for d in dims.values()}
        stds = {s.standard_id: s for s in db.query(Standard).filter(Standard.standard_id.in_(std_ids)).all()}
        for s in scores:
            d = dims.get(s.get("dimension_id"))
            if d is None:
                continue
            std = stds.get(d.standard_id)
            s["standard"] = {
                "standard_code": std.standard_code if std else "",
                "title": std.title if std else "",
                "version": std.version if std else "",
                "clause": d.clause or "",
            }
    return {
        "run_id": run.run_id,
        "subject_type": run.subject_type,
        "subject_id": run.subject_id,
        "run_at": run.run_at,
        "run_by": run.run_by,
        "overall_result": run.overall_result,
        "composite_grade": composite,
        "scores": scores,
        "flags": flags,
    }


# ── List / get ─────────────────────────────────────────────────────────────

@router.get("/operation")
def list_operation_records(
    state: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(OperationRecord)
    if state:
        q = q.filter(OperationRecord.state == state)
    rows = q.order_by(OperationRecord.updated_at.desc()).all()
    return [_serialise_record(r) for r in rows]


@router.get("/operation/{operation_id}")
def get_operation_record(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Operation record not found")
    return _serialise_record(rec)


# ── Run / list runs ────────────────────────────────────────────────────────

@router.post("/operation/{operation_id}/run", status_code=status.HTTP_201_CREATED)
def run_operation(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run an Operation-phase compliance check on this record.

    Triggered by a scheduler (cadence-driven), an incident, or a manual
    review. The engine is the same as Build / Deployment.
    """
    try:
        run = operation_lifecycle.run_operation_compliance(
            db, operation_id=operation_id, run_by=current_user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="ComplianceChecked",
        entity_type="PromptVersion",
        entity_id=operation_id,
        detail=json.dumps({
            "operation_id": operation_id,
            "run_id": run.run_id,
            "result": run.overall_result,
        }),
    ))
    db.commit()
    return _serialise_run(run, db)


@router.get("/operation/{operation_id}/runs")
def list_operation_runs(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    runs = operation_lifecycle.list_runs(db, operation_id)
    return [_serialise_run(r, db) for r in runs]


# ── Incidents ──────────────────────────────────────────────────────────────

@router.post("/operation/{operation_id}/incidents", status_code=status.HTTP_201_CREATED)
def append_incident(
    operation_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append an incident to the operation record.

    Body: { severity, category, summary, linked_run_id? }.
    severity ∈ {Low, Medium, High, Critical}.
    A High or Critical incident on an Active record flips state to Under Review.
    """
    severity = body.get("severity")
    category = body.get("category")
    summary = body.get("summary")
    if severity not in ("Low", "Medium", "High", "Critical"):
        raise HTTPException(status_code=422, detail="severity must be Low | Medium | High | Critical")
    if not category or not summary:
        raise HTTPException(status_code=422, detail="category and summary are required")

    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Operation record not found")
    if rec.state == "Retired":
        raise HTTPException(status_code=409, detail="Cannot append incident to a retired record")

    entry = operation_lifecycle.append_incident(
        db, rec,
        reporter=current_user.user_id,
        severity=severity,
        category=category,
        summary=summary,
        linked_run_id=body.get("linked_run_id"),
    )
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="DefectLogged",
        entity_type="PromptVersion",
        entity_id=operation_id,
        detail=json.dumps({
            "operation_id": operation_id,
            "incident_id": entry["incident_id"],
            "severity": severity,
            "category": category,
        }),
    ))
    db.commit()
    db.refresh(rec)
    return {"incident": entry, "record": _serialise_record(rec)}


# ── Retire / return to active ──────────────────────────────────────────────

@router.post("/operation/{operation_id}/retire")
def retire_operation(
    operation_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retire an operation record. Requires Checker or Admin (per
    OPERATION_SPEC §3 — auto-retire is parked).
    """
    if not _role_satisfies(current_user.role, "Checker"):
        raise HTTPException(status_code=403, detail="Retirement requires role Checker or Admin")

    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="reason is required")

    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Operation record not found")
    if rec.state == "Retired":
        raise HTTPException(status_code=409, detail="Already retired")

    rec.state = "Retired"
    rec.retired_at = _utcnow()
    rec.retired_reason = reason
    rec.updated_at = _utcnow()
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Retired",
        entity_type="PromptVersion",
        entity_id=operation_id,
        detail=json.dumps({"operation_id": operation_id, "reason": reason}),
    ))
    db.commit()
    db.refresh(rec)
    return _serialise_record(rec)


@router.post("/operation/{operation_id}/return-to-active")
def return_to_active(
    operation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Move an Under-Review record back to Active. Used after a
    remediation has cleared the latest incident or compliance failure."""
    if not _role_satisfies(current_user.role, "Checker"):
        raise HTTPException(status_code=403, detail="Return-to-active requires role Checker or Admin")

    rec = db.query(OperationRecord).filter(OperationRecord.operation_id == operation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Operation record not found")
    if rec.state != "Under Review":
        raise HTTPException(status_code=409, detail=f"Record state is '{rec.state}', not 'Under Review'")

    rec.state = "Active"
    rec.updated_at = _utcnow()
    db.commit()
    db.refresh(rec)
    return _serialise_record(rec)
