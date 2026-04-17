"""Brief CRUD endpoints — create, update, list, get, abandon, complete."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Brief, User
from app.schemas import BriefCreate, BriefOut, BriefUpdate

router = APIRouter(prefix="/briefs", tags=["briefs"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@router.post("", response_model=BriefOut, status_code=status.HTTP_201_CREATED)
def create_brief(
    body: BriefCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = Brief(
        brief_builder_id=current_user.user_id,
        client_name=body.client_name,
        business_owner_name=body.business_owner_name,
        business_owner_role=body.business_owner_role,
        status="In Progress",
        step_progress=1,
    )
    db.add(brief)
    db.flush()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefCreated",
        entity_type="Brief",
        entity_id=brief.brief_id,
        detail=json.dumps({"client": body.client_name}),
    ))
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)


@router.get("", response_model=list[BriefOut])
def list_briefs(
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Brief).filter(Brief.brief_builder_id == current_user.user_id)
    if status_filter:
        query = query.filter(Brief.status == status_filter)
    briefs = query.order_by(Brief.updated_at.desc()).all()
    return [BriefOut.model_validate(b) for b in briefs]


@router.get("/{brief_id}", response_model=BriefOut)
def get_brief(
    brief_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    return BriefOut.model_validate(brief)


@router.patch("/{brief_id}", response_model=BriefOut)
def update_brief(
    brief_id: str,
    body: BriefUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    if brief.status in ("Complete", "Archived"):
        raise HTTPException(status_code=409, detail="Brief is finalised")

    if body.step_progress is not None:
        brief.step_progress = body.step_progress
    if body.step_answers is not None:
        brief.step_answers = json.dumps(body.step_answers)
    if body.selected_guardrails is not None:
        brief.selected_guardrails = json.dumps(body.selected_guardrails)
    if body.quality_score is not None:
        brief.quality_score = body.quality_score
    if body.restructured_brief is not None:
        brief.restructured_brief = body.restructured_brief
    if body.client_name is not None:
        brief.client_name = body.client_name
    if body.business_owner_name is not None:
        brief.business_owner_name = body.business_owner_name
    if body.business_owner_role is not None:
        brief.business_owner_role = body.business_owner_role

    brief.updated_at = _utcnow()
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefUpdated",
        entity_type="Brief",
        entity_id=brief.brief_id,
        detail=json.dumps({"step": brief.step_progress}),
    ))
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)


@router.post("/{brief_id}/complete", response_model=BriefOut)
def complete_brief(
    brief_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    brief.status = "Complete"
    brief.submitted_at = _utcnow()
    brief.updated_at = _utcnow()
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefCompleted",
        entity_type="Brief",
        entity_id=brief.brief_id,
    ))
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)


@router.post("/{brief_id}/abandon", response_model=BriefOut)
def abandon_brief(
    brief_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    brief.status = "Abandoned"
    brief.updated_at = _utcnow()
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefAbandoned",
        entity_type="Brief",
        entity_id=brief.brief_id,
    ))
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)
