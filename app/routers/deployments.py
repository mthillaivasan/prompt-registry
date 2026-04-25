"""
Deployment record CRUD and form rendering endpoints — Block 13.

The form's field set lives in `form_fields` (seeded from
seed/form_fields.yml). This router exposes:

    GET  /forms/{form_code}                 → field config for the renderer
    POST /deployments                       → create draft deployment record
    GET  /deployments                       → list (filterable)
    GET  /deployments/{deployment_id}       → get one
    PUT  /deployments/{deployment_id}       → update form responses
    POST /deployments/{deployment_id}/submit → mark Pending Approval

Validation runs server-side against the same form_fields config the
renderer reads. No per-field Python validators — `services.form_validation`
loops the field rows and applies generic JSON rules.

Field-to-column dual-write: where the deployment form captures
`model_provider` and `output_destination`, those values are mirrored
onto the existing `prompts.ai_platform` and `prompts.output_destination`
columns at submission time, per DEPLOYMENT_FORM_SPEC §"Relationship to
existing prompts.ai_platform/output_destination". This keeps the legacy
columns populated through the transition.
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
    FormField,
    Prompt,
    PromptVersion,
    User,
)
from services import form_validation

router = APIRouter(tags=["deployments"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ── Form config rendering ──────────────────────────────────────────────────

def _serialise_field(f: FormField, dynamic_options: dict[str, list[dict]] | None = None) -> dict:
    options = json.loads(f.options) if f.options else None
    validation = json.loads(f.validation) if f.validation else None

    # Some select fields ship with `options: []` so the server can populate
    # them from a live source (e.g. user list). The dynamic_options map is
    # passed in by the form-config endpoint; the renderer treats values as
    # opaque {value, label} objects.
    dyn = (dynamic_options or {}).get(f.field_code)
    if dyn is not None:
        options = dyn

    return {
        "field_id": f.field_id,
        "field_code": f.field_code,
        "label": f.label,
        "help_text": f.help_text,
        "field_type": f.field_type,
        "options": options,
        "validation": validation,
        "sort_order": f.sort_order,
    }


def _user_options(db: Session, roles: list[str]) -> list[dict]:
    users = (
        db.query(User)
        .filter(User.is_active == True, User.role.in_(roles))  # noqa: E712
        .order_by(User.name)
        .all()
    )
    return [{"value": u.user_id, "label": f"{u.name} ({u.role})"} for u in users]


@router.get("/forms/{form_code}")
def get_form_config(
    form_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the form's field config for the renderer.

    Field rows where `options: []` are dynamically populated server-side
    for known field codes (currently `runtime_owner_id`, `approver_id`).
    The renderer treats every option uniformly as {value, label}; static
    options are returned as the raw string list, dynamic options as
    objects.
    """
    fields = (
        db.query(FormField)
        .filter(FormField.form_code == form_code, FormField.is_active == True)  # noqa: E712
        .order_by(FormField.sort_order)
        .all()
    )
    if not fields:
        raise HTTPException(status_code=404, detail=f"Form '{form_code}' has no active fields")

    dynamic = {
        "runtime_owner_id": _user_options(db, ["Maker", "Checker", "Admin"]),
        "approver_id": _user_options(db, ["Checker", "Admin"]),
    }

    return {
        "form_code": form_code,
        "fields": [_serialise_field(f, dynamic) for f in fields],
    }


# ── Deployment record CRUD ─────────────────────────────────────────────────

def _serialise_record(r: DeploymentRecord) -> dict:
    return {
        "deployment_id": r.deployment_id,
        "prompt_id": r.prompt_id,
        "version_id": r.version_id,
        "invocation_context": r.invocation_context,
        "ai_platform": r.ai_platform,
        "output_destination": r.output_destination,
        "runtime_owner_id": r.runtime_owner_id,
        "form_responses": json.loads(r.form_responses_json) if r.form_responses_json else {},
        "status": r.status,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
def create_deployment(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a Draft deployment record for a prompt version.

    Body: { "prompt_id": str, "version_id": str }.
    Form responses are filled by subsequent PUT calls.
    """
    prompt_id = body.get("prompt_id")
    version_id = body.get("version_id")
    if not prompt_id or not version_id:
        raise HTTPException(status_code=422, detail="prompt_id and version_id are required")

    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    version = db.query(PromptVersion).filter(PromptVersion.version_id == version_id).first()
    if not version or version.prompt_id != prompt_id:
        raise HTTPException(status_code=404, detail="Prompt version not found for this prompt")

    record = DeploymentRecord(
        prompt_id=prompt_id,
        version_id=version_id,
        runtime_owner_id=current_user.user_id,
        status="Draft",
    )
    db.add(record)
    db.flush()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Created",
        entity_type="PromptVersion",
        entity_id=record.deployment_id,
        detail=json.dumps({"deployment_id": record.deployment_id, "prompt_id": prompt_id, "version_id": version_id}),
    ))
    db.commit()
    db.refresh(record)
    return _serialise_record(record)


@router.get("/deployments")
def list_deployments(
    prompt_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(DeploymentRecord)
    if prompt_id:
        q = q.filter(DeploymentRecord.prompt_id == prompt_id)
    if status_filter:
        q = q.filter(DeploymentRecord.status == status_filter)
    rows = q.order_by(DeploymentRecord.updated_at.desc()).all()
    return [_serialise_record(r) for r in rows]


@router.get("/deployments/{deployment_id}")
def get_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rec = db.query(DeploymentRecord).filter(DeploymentRecord.deployment_id == deployment_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment record not found")
    return _serialise_record(rec)


@router.put("/deployments/{deployment_id}")
def update_deployment_responses(
    deployment_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the form responses on a Draft deployment record.

    Body: { "responses": {field_code: value, ...} }.
    Validation runs but blocking errors are returned alongside the saved
    record — drafts may be incomplete. The submit endpoint enforces full
    validity before transitioning to Pending Approval.
    """
    rec = db.query(DeploymentRecord).filter(DeploymentRecord.deployment_id == deployment_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment record not found")
    if rec.status not in ("Draft", "Rejected"):
        raise HTTPException(status_code=409, detail=f"Cannot edit a record in status '{rec.status}'")

    responses = body.get("responses") or {}

    fields = (
        db.query(FormField)
        .filter(FormField.form_code == "deployment_form", FormField.is_active == True)  # noqa: E712
        .order_by(FormField.sort_order)
        .all()
    )
    errors, normalised = form_validation.validate_form_response(fields, responses)

    rec.form_responses_json = json.dumps(normalised)
    # Convenience columns mirrored from form responses:
    rec.invocation_context = body.get("invocation_context") or _summary_from_responses(normalised)
    rec.ai_platform = normalised.get("model_provider") or rec.ai_platform
    rec.output_destination = normalised.get("output_destination") or rec.output_destination
    if normalised.get("runtime_owner_id"):
        rec.runtime_owner_id = normalised["runtime_owner_id"]
    rec.updated_at = _utcnow()

    db.commit()
    db.refresh(rec)
    return {"record": _serialise_record(rec), "errors": errors}


def _summary_from_responses(responses: dict) -> str | None:
    """Build a compact human-readable invocation context summary from form
    responses. Used for display in lists; the structured detail stays in
    `form_responses_json`."""
    if not responses:
        return None
    parts = []
    if responses.get("invocation_trigger"):
        parts.append(f"Trigger: {responses['invocation_trigger']}")
    if responses.get("invocation_frequency_per_day"):
        parts.append(f"Freq/day: {responses['invocation_frequency_per_day']}")
    if responses.get("output_destination"):
        parts.append(f"Output → {responses['output_destination']}")
    return "; ".join(parts) if parts else None


@router.post("/deployments/{deployment_id}/submit")
def submit_deployment(
    deployment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Transition Draft → Pending Approval after enforcing full validation.

    The compliance engine (Block 15) and gate (Block 16) act on records
    in status `Pending Approval`.
    """
    rec = db.query(DeploymentRecord).filter(DeploymentRecord.deployment_id == deployment_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Deployment record not found")
    if rec.status not in ("Draft", "Rejected"):
        raise HTTPException(status_code=409, detail=f"Cannot submit a record in status '{rec.status}'")

    fields = (
        db.query(FormField)
        .filter(FormField.form_code == "deployment_form", FormField.is_active == True)  # noqa: E712
        .order_by(FormField.sort_order)
        .all()
    )
    responses = json.loads(rec.form_responses_json) if rec.form_responses_json else {}
    errors, _normalised = form_validation.validate_form_response(fields, responses)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    rec.status = "Pending Approval"
    rec.updated_at = _utcnow()

    # Dual-write to legacy prompt columns per DEPLOYMENT_FORM_SPEC.
    if rec.ai_platform or rec.output_destination:
        prompt = db.query(Prompt).filter(Prompt.prompt_id == rec.prompt_id).first()
        if prompt:
            if rec.ai_platform:
                prompt.ai_platform = rec.ai_platform
            if rec.output_destination:
                prompt.output_destination = rec.output_destination
            prompt.updated_at = _utcnow()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Edited",
        entity_type="PromptVersion",
        entity_id=rec.deployment_id,
        detail=json.dumps({"deployment_id": rec.deployment_id, "transition": "Draft→Pending Approval"}),
    ))
    db.commit()
    db.refresh(rec)
    return _serialise_record(rec)
