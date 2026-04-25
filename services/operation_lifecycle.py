"""
Operation-phase lifecycle helpers — Block 18.

Mirrors the deployment_compliance pattern: a serialiser converts an
operation_record into the (scoring_input_text, metadata) pair the generic
engine expects, plus a dispatch helper.

The engine itself is unchanged. No phase branches.
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import (
    ComplianceRun,
    DeploymentRecord,
    OperationRecord,
    Phase,
    Prompt,
    PromptVersion,
)
from services import compliance_engine


_DEFAULT_REVIEW_CADENCE_DAYS = 90  # final fallback if nothing in config — see OPERATION_SPEC §3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_cadence_days(db: Session, deployment: DeploymentRecord) -> int:
    """Resolve the cadence in priority order:

    1. deployment form response `change_review_frequency_days`
    2. phases.operation default if columnar (currently absent — see PHASE3)
    3. global default 90
    """
    responses = (
        json.loads(deployment.form_responses_json)
        if deployment.form_responses_json
        else {}
    )
    raw = responses.get("change_review_frequency_days")
    if raw is not None and str(raw).strip():
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass

    phase = db.query(Phase).filter(Phase.code == "operation").one_or_none()
    if phase is not None:
        # Phase row carries no cadence column today — see OPERATION_SPEC §3
        # for the planned addition. Fall through to the default.
        pass

    return _DEFAULT_REVIEW_CADENCE_DAYS


def create_operation_record_for_deployment(
    db: Session, deployment: DeploymentRecord
) -> OperationRecord:
    """Idempotent: returns the existing record if one exists, otherwise
    creates a new Active operation record and computes next_review_date.
    Called from the Block 16 gate when a deployment is Approved."""
    existing = (
        db.query(OperationRecord)
        .filter(OperationRecord.deployment_id == deployment.deployment_id)
        .one_or_none()
    )
    if existing is not None:
        return existing

    cadence = resolve_cadence_days(db, deployment)
    now = _utcnow()
    record = OperationRecord(
        deployment_id=deployment.deployment_id,
        state="Active",
        next_review_date=_isoformat(now + timedelta(days=cadence)),
        review_cadence_days=cadence,
        incidents_json="[]",
    )
    db.add(record)
    db.flush()
    return record


def append_incident(
    db: Session,
    record: OperationRecord,
    *,
    reporter: str,
    severity: str,
    category: str,
    summary: str,
    linked_run_id: str | None = None,
) -> dict[str, Any]:
    """Append an incident; if severity is at or above the configured
    threshold, flip state to Under Review."""
    import uuid

    incidents = json.loads(record.incidents_json) if record.incidents_json else []
    entry = {
        "incident_id": str(uuid.uuid4()),
        "timestamp": _isoformat(_utcnow()),
        "reporter": reporter,
        "severity": severity,
        "category": category,
        "summary": summary,
        "linked_run_id": linked_run_id,
        "retire_recommended": False,
    }
    incidents.append(entry)
    record.incidents_json = json.dumps(incidents)
    record.updated_at = _isoformat(_utcnow())

    # Severity threshold lives on the phases.operation row when extended;
    # for Phase 2 default to High per OPERATION_SPEC §4.
    if severity in ("High", "Critical") and record.state == "Active":
        record.state = "Under Review"

    return entry


def serialise_operation_record(
    db: Session, record: OperationRecord
) -> tuple[str, dict[str, Any]]:
    """Render the record for the scoring model.

    Includes a brief summary of the underlying prompt + deployment plus
    aggregated incident telemetry. Detailed incident entries are not
    embedded — the scoring model receives counts and severities, not
    free-text histories.
    """
    deployment = (
        db.query(DeploymentRecord)
        .filter(DeploymentRecord.deployment_id == record.deployment_id)
        .one_or_none()
    )

    prompt = None
    version = None
    if deployment is not None:
        prompt = db.query(Prompt).filter(Prompt.prompt_id == deployment.prompt_id).one_or_none()
        version = (
            db.query(PromptVersion)
            .filter(PromptVersion.version_id == deployment.version_id)
            .one_or_none()
        )

    incidents = json.loads(record.incidents_json) if record.incidents_json else []
    severities: dict[str, int] = {}
    for inc in incidents:
        sev = inc.get("severity", "Low")
        severities[sev] = severities.get(sev, 0) + 1

    lines: list[str] = []
    if prompt is not None:
        lines.append(f"PROMPT_TITLE: {prompt.title}")
        lines.append(f"PROMPT_TYPE: {prompt.prompt_type}")
        lines.append(f"PROMPT_RISK_TIER: {prompt.risk_tier}")
    if version is not None:
        lines.append(f"PROMPT_VERSION: v{version.version_number}")
    lines.append(f"OPERATION_STATE: {record.state}")
    lines.append(f"OPERATION_REVIEW_CADENCE_DAYS: {record.review_cadence_days}")
    lines.append(f"OPERATION_NEXT_REVIEW_DATE: {record.next_review_date or ''}")
    lines.append(f"OPERATION_INCIDENT_COUNT: {len(incidents)}")
    for sev, count in sorted(severities.items()):
        lines.append(f"OPERATION_INCIDENT_COUNT_{sev.upper()}: {count}")
    if record.retired_at:
        lines.append(f"OPERATION_RETIRED_AT: {record.retired_at}")
        lines.append(f"OPERATION_RETIRED_REASON: {record.retired_reason or ''}")

    text = "\n".join(lines)

    metadata: dict[str, Any] = {}
    if prompt is not None:
        metadata["prompt_type"] = prompt.prompt_type
        metadata["input_type"] = prompt.input_type
        metadata["risk_tier"] = prompt.risk_tier
    metadata["incident_count"] = len(incidents)
    metadata["has_critical_incidents"] = severities.get("Critical", 0) > 0
    metadata["has_high_incidents"] = severities.get("High", 0) > 0
    metadata["state"] = record.state

    return text, metadata


def run_operation_compliance(
    db: Session,
    *,
    operation_id: str,
    run_by: str,
    score_provider: Callable[[str, str], str] | None = None,
) -> ComplianceRun:
    """Run the Operation-phase compliance engine on an operation record.

    On success: bumps next_review_date by cadence_days. On failure:
    bumps by cadence_days // 4 so the next re-evaluation arrives sooner.
    """
    record = (
        db.query(OperationRecord)
        .filter(OperationRecord.operation_id == operation_id)
        .one_or_none()
    )
    if record is None:
        raise ValueError(f"OperationRecord '{operation_id}' not found")

    text, metadata = serialise_operation_record(db, record)

    run = compliance_engine.run_phase_compliance(
        db,
        phase_code="operation",
        subject_type="operation_record",
        subject_id=record.operation_id,
        run_by=run_by,
        scoring_input_text=text,
        metadata=metadata,
        score_provider=score_provider,
    )

    cadence = record.review_cadence_days or _DEFAULT_REVIEW_CADENCE_DAYS
    if run.overall_result == "Fail":
        bump_days = max(1, cadence // 4)
        if record.state == "Active":
            record.state = "Under Review"
    else:
        bump_days = cadence
        if record.state == "Under Review":
            record.state = "Active"

    record.next_review_date = _isoformat(_utcnow() + timedelta(days=bump_days))
    record.updated_at = _isoformat(_utcnow())
    db.commit()
    db.refresh(run)
    return run


def get_latest_run(db: Session, operation_id: str) -> ComplianceRun | None:
    return (
        db.query(ComplianceRun)
        .filter(
            ComplianceRun.subject_type == "operation_record",
            ComplianceRun.subject_id == operation_id,
        )
        .order_by(ComplianceRun.run_at.desc())
        .first()
    )


def list_runs(db: Session, operation_id: str) -> list[ComplianceRun]:
    return (
        db.query(ComplianceRun)
        .filter(
            ComplianceRun.subject_type == "operation_record",
            ComplianceRun.subject_id == operation_id,
        )
        .order_by(ComplianceRun.run_at.desc())
        .all()
    )
