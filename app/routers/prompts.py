"""Prompt CRUD endpoints — create, list, get, update."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Prompt, PromptVersion, User
from app.schemas import (
    PromptCreate,
    PromptDetail,
    PromptOut,
    PromptUpdate,
    PromptVersionOut,
)

router = APIRouter(prefix="/prompts", tags=["prompts"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# Allowed status transitions. None means transition is allowed from anywhere.
_TRANSITIONS: dict[str, set[str]] = {
    "Draft": {"Active", "Suspended", "Retired"},
    "Active": {"Review Required", "Suspended", "Retired"},
    "Review Required": {"Active", "Suspended", "Retired"},
    "Suspended": {"Active", "Retired"},
    "Retired": set(),  # terminal state
}


def _build_detail(prompt: Prompt, db: Session) -> PromptDetail:
    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt.prompt_id)
        .order_by(PromptVersion.version_number.asc())
        .all()
    )
    active = next((v for v in versions if v.is_active), None)
    return PromptDetail(
        **PromptOut.model_validate(prompt).model_dump(),
        versions=[PromptVersionOut.model_validate(v) for v in versions],
        active_version=PromptVersionOut.model_validate(active) if active else None,
    )


@router.post("", response_model=PromptDetail, status_code=status.HTTP_201_CREATED)
def create_prompt(
    body: PromptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = Prompt(
        title=body.title,
        prompt_type=body.prompt_type,
        # Transitional dual-write: deployment_target deprecated; new callers
        # set ai_platform + output_destination instead. See schemas.py.
        deployment_target=body.deployment_target,
        ai_platform=body.ai_platform,
        output_destination=body.output_destination,
        input_type=body.input_type,
        output_type=body.output_type,
        risk_tier=body.risk_tier,
        owner_id=current_user.user_id,
        status="Draft",
        review_cadence_days=body.review_cadence_days,
    )
    db.add(prompt)
    db.flush()  # populate prompt_id

    version = PromptVersion(
        prompt_id=prompt.prompt_id,
        version_number=1,
        previous_version_id=None,
        prompt_text=body.prompt_text,
        change_summary=body.change_summary,
        created_by=current_user.user_id,
        is_active=False,
    )
    db.add(version)
    db.flush()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Created",
        entity_type="Prompt",
        entity_id=prompt.prompt_id,
        detail=json.dumps({
            "title": prompt.title,
            "version_id": version.version_id,
            "version_number": 1,
        }),
    ))

    db.commit()
    db.refresh(prompt)
    return _build_detail(prompt, db)


@router.get("", response_model=list[PromptOut])
def list_prompts(
    status_filter: str | None = Query(default=None, alias="status"),
    risk_tier: str | None = Query(default=None),
    prompt_type: str | None = Query(default=None),
    owner_id: str | None = Query(default=None),
    search: str | None = Query(default=None, description="Case-insensitive title search"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Prompt)
    if status_filter:
        query = query.filter(Prompt.status == status_filter)
    if risk_tier:
        query = query.filter(Prompt.risk_tier == risk_tier)
    if prompt_type:
        query = query.filter(Prompt.prompt_type == prompt_type)
    if owner_id:
        query = query.filter(Prompt.owner_id == owner_id)
    if search:
        query = query.filter(Prompt.title.ilike(f"%{search}%"))
    try:
        prompts = query.order_by(Prompt.updated_at.desc()).all()
        return [PromptOut.model_validate(p) for p in prompts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/{prompt_id}", response_model=PromptDetail)
def get_prompt(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _build_detail(prompt, db)


@router.patch("/{prompt_id}", response_model=PromptDetail)
def update_prompt(
    prompt_id: str,
    body: PromptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    changes: dict[str, object] = {}
    audit_action = "Edited"

    if body.title is not None and body.title != prompt.title:
        changes["title"] = {"from": prompt.title, "to": body.title}
        prompt.title = body.title

    if body.status is not None and body.status != prompt.status:
        old = prompt.status
        new = body.status
        if new not in _TRANSITIONS.get(old, set()):
            raise HTTPException(
                status_code=409,
                detail=f"Invalid status transition: {old} → {new}",
            )
        changes["status"] = {"from": old, "to": new}
        prompt.status = new
        if new == "Active":
            audit_action = "Activated"
        elif new == "Retired":
            audit_action = "Retired"
        # Suspended/Review Required keep audit_action = "Edited"

    if body.approver_id is not None:
        approver = db.query(User).filter(User.user_id == body.approver_id).first()
        if not approver:
            raise HTTPException(status_code=400, detail="Approver user not found")
        changes["approver_id"] = {"from": prompt.approver_id, "to": body.approver_id}
        prompt.approver_id = body.approver_id

    if body.review_cadence_days is not None and body.review_cadence_days != prompt.review_cadence_days:
        changes["review_cadence_days"] = {
            "from": prompt.review_cadence_days,
            "to": body.review_cadence_days,
        }
        prompt.review_cadence_days = body.review_cadence_days

    if body.next_review_date is not None and body.next_review_date != prompt.next_review_date:
        changes["next_review_date"] = {
            "from": prompt.next_review_date,
            "to": body.next_review_date,
        }
        prompt.next_review_date = body.next_review_date

    if not changes:
        return _build_detail(prompt, db)

    prompt.updated_at = _utcnow()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action=audit_action,
        entity_type="Prompt",
        entity_id=prompt.prompt_id,
        detail=json.dumps({"changes": changes}),
    ))

    db.commit()
    db.refresh(prompt)
    return _build_detail(prompt, db)
