"""
Deployment-phase compliance — Block 15.

Per DEPLOYMENT_COMPLIANCE_SPEC.md, the engine itself is unchanged. This
module supplies two helpers and one entry point:

    serialise_deployment_record(db, record) -> (str, dict)
        Turns a DeploymentRecord into the (scoring_input_text, metadata)
        pair that services.compliance_engine.run_phase_compliance accepts.

    run_deployment_compliance(db, deployment_id, run_by, score_provider=None)
        Loads the record, calls the serialiser, dispatches to
        run_phase_compliance with phase_code='deployment'. Returns the
        ComplianceRun row.

Configuration-first: the serialiser does not list field codes by name.
It walks `form_responses_json` keys and prefixes each with `DEPLOYMENT_`.
Adding a form field appears automatically in the scoring input.
"""

import json
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.models import (
    ComplianceRun,
    DeploymentRecord,
    Prompt,
    PromptVersion,
)
from services import compliance_engine


def _format_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) if v else ""
    if v is None:
        return ""
    return str(v)


def serialise_deployment_record(
    db: Session, record: DeploymentRecord
) -> tuple[str, dict[str, Any]]:
    """Render the record as (scoring_input_text, applicability_metadata).

    The scoring text is a deterministic, line-oriented view: prompt
    context block followed by every form response, prefixed
    `DEPLOYMENT_<FIELD_CODE>:`. The metadata dict carries flags that
    Deployment-phase applicability rules read.
    """
    prompt = db.query(Prompt).filter(Prompt.prompt_id == record.prompt_id).one_or_none()
    version = db.query(PromptVersion).filter(
        PromptVersion.version_id == record.version_id
    ).one_or_none()

    responses = (
        json.loads(record.form_responses_json) if record.form_responses_json else {}
    )

    lines: list[str] = []
    if prompt is not None:
        lines.append(f"PROMPT_TITLE: {prompt.title}")
        lines.append(f"PROMPT_TYPE: {prompt.prompt_type}")
        lines.append(f"PROMPT_RISK_TIER: {prompt.risk_tier}")
    if version is not None:
        lines.append(f"PROMPT_VERSION: v{version.version_number}")
        lines.append("PROMPT_TEXT:")
        lines.append(version.prompt_text)
    if responses:
        lines.append("")
        for code in sorted(responses.keys()):
            lines.append(f"DEPLOYMENT_{code.upper()}: {_format_value(responses[code])}")

    scoring_input_text = "\n".join(lines)

    # Applicability metadata. Build context from the prompt and derive flags
    # from form responses.
    metadata: dict[str, Any] = {}
    if prompt is not None:
        metadata["prompt_type"] = prompt.prompt_type
        metadata["input_type"] = prompt.input_type
        metadata["risk_tier"] = prompt.risk_tier
    metadata["input_user_supplied"] = bool(responses.get("input_user_supplied"))
    metadata["output_executed_by_machine"] = bool(
        responses.get("output_executed_by_machine")
    )
    categories = responses.get("input_data_categories") or []
    if isinstance(categories, str):
        categories = [categories]
    metadata["personal_data_present"] = "personal_data" in categories

    return scoring_input_text, metadata


def run_deployment_compliance(
    db: Session,
    *,
    deployment_id: str,
    run_by: str,
    score_provider: Callable[[str, str], str] | None = None,
) -> ComplianceRun:
    """Run a Deployment-phase compliance check on a DeploymentRecord."""
    record = db.query(DeploymentRecord).filter(
        DeploymentRecord.deployment_id == deployment_id
    ).one_or_none()
    if record is None:
        raise ValueError(f"DeploymentRecord '{deployment_id}' not found")

    scoring_input_text, metadata = serialise_deployment_record(db, record)

    return compliance_engine.run_phase_compliance(
        db,
        phase_code="deployment",
        subject_type="deployment_record",
        subject_id=record.deployment_id,
        run_by=run_by,
        scoring_input_text=scoring_input_text,
        metadata=metadata,
        score_provider=score_provider,
    )


def get_latest_run(db: Session, deployment_id: str) -> ComplianceRun | None:
    """Return the most recent ComplianceRun for the given deployment record."""
    return (
        db.query(ComplianceRun)
        .filter(
            ComplianceRun.subject_type == "deployment_record",
            ComplianceRun.subject_id == deployment_id,
        )
        .order_by(ComplianceRun.run_at.desc())
        .first()
    )
