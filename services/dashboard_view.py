"""
Dashboard view assembler — Block 20.

Reads from records and phase config, returns a row payload per prompt
with `(state, label)` for each of the four lifecycle phases. Generic:
the cell-vocabulary table in DASHBOARD_SPEC §2 lives here as data, not
code branches on phase identity.

The renderer (UI) maps `state` → colour through a single lookup. The
service does not know about colours.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Brief,
    ComplianceCheck,
    ComplianceRun,
    DeploymentRecord,
    GateDecision,
    OperationRecord,
    Phase,
    Prompt,
    PromptVersion,
)


_NEUTRAL_CELL = {"state": "—", "label": "—"}


def _composite_to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _label_for_compliance(result: str | None, grade: int | None) -> tuple[str, str]:
    """Map compliance result + grade to (state_word, label)."""
    if result == "Pass":
        return "Pass", f"✓ Pass {grade}" if grade is not None else "✓ Pass"
    if result == "Pass with warnings":
        return "PWW", f"PWW {grade}" if grade is not None else "PWW"
    if result == "Fail":
        return "Fail", f"Fail {grade} 🚫" if grade is not None else "Fail 🚫"
    return _NEUTRAL_CELL["state"], _NEUTRAL_CELL["label"]


def _brief_cell(db: Session, prompt: Prompt) -> dict[str, Any]:
    """Brief column. Briefs link forward via brief.resulting_prompt_id;
    if a brief points to this prompt and is Complete, the cell is
    Complete. If no brief exists for this prompt, treat as Complete
    (legacy prompts that pre-date Brief Builder still appear sensibly)."""
    brief = (
        db.query(Brief)
        .filter(Brief.resulting_prompt_id == prompt.prompt_id)
        .order_by(Brief.updated_at.desc())
        .first()
    )
    if brief is None:
        return {"state": "Complete", "label": "✓ Complete"}
    if brief.status == "Complete":
        return {"state": "Complete", "label": "✓ Complete", "brief_id": brief.brief_id}
    if brief.status == "In Progress":
        return {"state": "In progress", "label": "In progress", "brief_id": brief.brief_id}
    return {"state": "—", "label": brief.status, "brief_id": brief.brief_id}


def _build_cell(db: Session, prompt: Prompt) -> tuple[dict[str, Any], dict | None]:
    """Build column. Reads compliance_runs first (Phase 2 path); falls
    back to compliance_checks (legacy path) so prompts approved before
    Block 9 still render. Returns (cell, gate_decision_or_none)."""
    # Find the active version (or most recent) for this prompt
    version = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt.prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .first()
    )
    if version is None:
        return dict(_NEUTRAL_CELL), None

    # Phase 2 run preferred
    build_phase = db.query(Phase).filter(Phase.code == "build").one_or_none()
    run_v2 = None
    if build_phase is not None:
        run_v2 = (
            db.query(ComplianceRun)
            .filter(
                ComplianceRun.subject_type == "prompt_version",
                ComplianceRun.subject_id == version.version_id,
                ComplianceRun.phase_id == build_phase.phase_id,
            )
            .order_by(ComplianceRun.run_at.desc())
            .first()
        )

    if run_v2 is not None:
        state, label = _label_for_compliance(
            run_v2.overall_result,
            _composite_to_int(run_v2.composite_grade),
        )
        cell = {
            "state": state,
            "label": label,
            "grade": _composite_to_int(run_v2.composite_grade),
            "run_id": run_v2.run_id,
        }
        gate = (
            db.query(GateDecision)
            .filter(
                GateDecision.subject_type == "prompt_version",
                GateDecision.subject_id == version.version_id,
                GateDecision.decision == "Approved",
            )
            .order_by(GateDecision.decided_at.desc())
            .first()
        )
        return cell, gate

    # Legacy compliance_checks fall-back. Read overall_result + gold_standard.
    legacy = (
        db.query(ComplianceCheck)
        .filter(ComplianceCheck.version_id == version.version_id)
        .order_by(ComplianceCheck.run_at.desc())
        .first()
    )
    if legacy is None:
        return dict(_NEUTRAL_CELL), None

    grade = None
    if legacy.gold_standard:
        try:
            grade = int(round(float(json.loads(legacy.gold_standard).get("composite", 0))))
        except (TypeError, ValueError, json.JSONDecodeError):
            grade = None
    state, label = _label_for_compliance(legacy.overall_result, grade)
    cell = {"state": state, "label": label, "grade": grade, "check_id": legacy.check_id}
    return cell, None


def _deployment_cell(
    db: Session, prompt: Prompt
) -> tuple[dict[str, Any], dict | None]:
    """Deployment column."""
    rec = (
        db.query(DeploymentRecord)
        .filter(DeploymentRecord.prompt_id == prompt.prompt_id)
        .order_by(DeploymentRecord.updated_at.desc())
        .first()
    )
    if rec is None:
        return dict(_NEUTRAL_CELL), None

    base = {"deployment_id": rec.deployment_id}
    if rec.status == "Approved":
        cell = {**base, "state": "Approved", "label": "✓ Approved"}
    elif rec.status == "Rejected":
        cell = {**base, "state": "Rejected", "label": "Rejected"}
    elif rec.status == "Pending Approval":
        cell = {**base, "state": "Pending", "label": "Pending"}
    elif rec.status == "Draft":
        cell = {**base, "state": "In progress", "label": "Draft"}
    elif rec.status == "Withdrawn":
        cell = {**base, "state": "—", "label": "Withdrawn"}
    else:
        cell = {**base, "state": "—", "label": rec.status}

    gate = (
        db.query(GateDecision)
        .filter(
            GateDecision.subject_type == "deployment_record",
            GateDecision.subject_id == rec.deployment_id,
            GateDecision.decision == "Approved",
        )
        .order_by(GateDecision.decided_at.desc())
        .first()
    )
    return cell, gate


def _operation_cell(db: Session, prompt: Prompt) -> dict[str, Any]:
    """Operation column."""
    deployment = (
        db.query(DeploymentRecord)
        .filter(
            DeploymentRecord.prompt_id == prompt.prompt_id,
            DeploymentRecord.status == "Approved",
        )
        .order_by(DeploymentRecord.updated_at.desc())
        .first()
    )
    if deployment is None:
        return dict(_NEUTRAL_CELL)

    rec = (
        db.query(OperationRecord)
        .filter(OperationRecord.deployment_id == deployment.deployment_id)
        .first()
    )
    if rec is None:
        return dict(_NEUTRAL_CELL)

    return {
        "state": rec.state,
        "label": rec.state,
        "operation_id": rec.operation_id,
    }


def _gate_summary(decision: GateDecision | None) -> dict | None:
    if decision is None:
        return None
    return {
        "decided_at": decision.decided_at,
        "decided_by": decision.decided_by,
        "rationale": decision.rationale,
        "run_id": decision.run_id,
    }


def build_dashboard(
    db: Session,
    *,
    owner_id: str | None = None,
    risk_tier: str | None = None,
    lifecycle_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Return the dashboard rows.

    `owner_id` — restrict to prompts owned by this user. None = all.
    `risk_tier` — restrict to prompts at this risk tier.
    `lifecycle_filter` — one of:
        at-brief, at-build, at-deployment, at-operation, retired-only.
        None means no lifecycle filter.
    """
    q = db.query(Prompt)
    if owner_id:
        q = q.filter(Prompt.owner_id == owner_id)
    if risk_tier:
        q = q.filter(Prompt.risk_tier == risk_tier)
    prompts = q.order_by(Prompt.updated_at.desc()).all()

    rows: list[dict[str, Any]] = []
    for p in prompts:
        brief = _brief_cell(db, p)
        build, build_gate = _build_cell(db, p)
        deployment, deployment_gate = _deployment_cell(db, p)
        operation = _operation_cell(db, p)

        row = {
            "prompt_id": p.prompt_id,
            "title": p.title,
            "prompt_type": p.prompt_type,
            "risk_tier": p.risk_tier,
            "owner_id": p.owner_id,
            "updated_at": p.updated_at,
            "brief": brief,
            "build": build,
            "build_gate": _gate_summary(build_gate),
            "deployment": deployment,
            "deployment_gate": _gate_summary(deployment_gate),
            "operation": operation,
        }

        if lifecycle_filter:
            position = _lifecycle_position(row)
            if position != lifecycle_filter:
                continue

        rows.append(row)
    return rows


def _lifecycle_position(row: dict[str, Any]) -> str:
    """Where on the lifecycle sits this row's furthest-right populated cell."""
    if row["operation"]["state"] == "Retired":
        return "retired-only"
    if row["operation"]["state"] != "—":
        return "at-operation"
    if row["deployment"]["state"] != "—":
        return "at-deployment"
    if row["build"]["state"] != "—":
        return "at-build"
    return "at-brief"
