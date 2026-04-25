"""
Build → Deployment gate router — Block 22 (fixes F21.1).

The Block 16 deployment gate has no Build counterpart. Without it the
dashboard's `build_gate` marker never lights up for any flow-driven
prompt and a Build-approved prompt cannot move to Deployment without a
direct DB write.

This router fires the Build gate. Same shape as the deployment gate:

    POST /prompt-versions/{version_id}/gate-decision
    GET  /prompt-versions/{version_id}/gate-decisions

Reads gate config from the `gates` table; never branches on phase code.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    AuditLog,
    ComplianceRun,
    Gate,
    GateDecision,
    Phase,
    PromptVersion,
    User,
)

router = APIRouter(tags=["build-gate"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


_ROLE_RANK = {"Maker": 1, "Checker": 2, "Admin": 3}


def _role_satisfies(actual: str, required: str) -> bool:
    return _ROLE_RANK.get(actual, 0) >= _ROLE_RANK.get(required, 999)


def _gate_for_phase(db: Session, phase_code: str) -> Gate | None:
    phase = db.query(Phase).filter(Phase.code == phase_code).one_or_none()
    if phase is None:
        return None
    return (
        db.query(Gate)
        .filter(Gate.from_phase_id == phase.phase_id, Gate.is_active == True)  # noqa: E712
        .first()
    )


def _latest_build_run_for_version(db: Session, version_id: str) -> ComplianceRun | None:
    phase = db.query(Phase).filter(Phase.code == "build").one_or_none()
    if phase is None:
        return None
    return (
        db.query(ComplianceRun)
        .filter(
            ComplianceRun.subject_type == "prompt_version",
            ComplianceRun.subject_id == version_id,
            ComplianceRun.phase_id == phase.phase_id,
        )
        .order_by(ComplianceRun.run_at.desc())
        .first()
    )


@router.post("/prompt-versions/{version_id}/gate-decision", status_code=status.HTTP_201_CREATED)
def decide_build_gate(
    version_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve or reject a Build run, gating the prompt version into
    Deployment. Symmetric with the Block 16 deployment gate.

    Body:
        decision: 'Approved' | 'Rejected'
        rationale: str — required when gate config says so

    Pre-conditions read from the `gates` config:
        - Build run for this version must exist (in compliance_runs).
        - User role must satisfy gate.approver_role.
        - rationale required when gate.rationale_required is true.
        - Cannot approve a run whose overall_result is 'Fail'.
        - Cannot fire a second decision on a version that already has
          an Approved or Rejected gate row.
    """
    decision = body.get("decision")
    rationale = (body.get("rationale") or "").strip()
    if decision not in ("Approved", "Rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'Approved' or 'Rejected'")

    version = db.query(PromptVersion).filter(PromptVersion.version_id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    gate = _gate_for_phase(db, "build")
    if gate is None:
        raise HTTPException(status_code=500, detail="Build gate is not configured")

    if not _role_satisfies(current_user.role, gate.approver_role):
        raise HTTPException(
            status_code=403,
            detail=f"Gate '{gate.code}' requires role '{gate.approver_role}'; you are '{current_user.role}'",
        )

    if gate.rationale_required and not rationale:
        raise HTTPException(status_code=422, detail="Rationale is required for this gate")

    run = _latest_build_run_for_version(db, version_id)
    if run is None:
        raise HTTPException(
            status_code=409,
            detail="No Build compliance run for this version; run /compliance-checks first",
        )
    if decision == "Approved" and run.overall_result == "Fail":
        raise HTTPException(
            status_code=409,
            detail="Cannot approve a version whose latest Build compliance run is 'Fail'",
        )

    existing = (
        db.query(GateDecision)
        .filter(
            GateDecision.gate_id == gate.gate_id,
            GateDecision.subject_type == "prompt_version",
            GateDecision.subject_id == version_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Build gate already fired for this version ({existing.decision})",
        )

    gd = GateDecision(
        gate_id=gate.gate_id,
        subject_type="prompt_version",
        subject_id=version_id,
        run_id=run.run_id,
        decision=decision,
        decided_by=current_user.user_id,
        rationale=rationale or None,
    )
    db.add(gd)

    if decision == "Approved":
        version.approved_by = current_user.user_id
        version.approved_at = _utcnow()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Approved" if decision == "Approved" else "DefectLogged",
        entity_type="PromptVersion",
        entity_id=version_id,
        detail=json.dumps({
            "version_id": version_id,
            "gate": gate.code,
            "decision": decision,
            "run_id": run.run_id,
            "rationale": rationale or None,
        }),
    ))

    db.commit()
    db.refresh(gd)
    return {
        "decision_id": gd.decision_id,
        "gate_code": gate.code,
        "decision": gd.decision,
        "decided_by": gd.decided_by,
        "decided_at": gd.decided_at,
        "rationale": gd.rationale,
        "version_id": version_id,
        "run_id": run.run_id,
    }


@router.get("/prompt-versions/{version_id}/gate-decisions")
def list_build_gate_decisions(
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(GateDecision)
        .filter(
            GateDecision.subject_type == "prompt_version",
            GateDecision.subject_id == version_id,
        )
        .order_by(GateDecision.decided_at.desc())
        .all()
    )
    return [
        {
            "decision_id": gd.decision_id,
            "gate_id": gd.gate_id,
            "decision": gd.decision,
            "decided_by": gd.decided_by,
            "decided_at": gd.decided_at,
            "rationale": gd.rationale,
            "run_id": gd.run_id,
        }
        for gd in rows
    ]
