"""Prompt version endpoints — create new version, list, get, activate."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Prompt, PromptVersion, User
from app.schemas import PromptVersionOut, VersionCreate

router = APIRouter(prefix="/prompts/{prompt_id}/versions", tags=["versions"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _get_prompt(prompt_id: str, db: Session) -> Prompt:
    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return prompt


@router.post("", response_model=PromptVersionOut, status_code=status.HTTP_201_CREATED)
def create_version(
    prompt_id: str,
    body: VersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = _get_prompt(prompt_id, db)
    if prompt.status == "Retired":
        raise HTTPException(status_code=409, detail="Cannot add version to a Retired prompt")

    latest = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .first()
    )
    next_number = (latest.version_number + 1) if latest else 1

    version = PromptVersion(
        prompt_id=prompt_id,
        version_number=next_number,
        previous_version_id=latest.version_id if latest else None,
        prompt_text=body.prompt_text,
        change_summary=body.change_summary,
        created_by=current_user.user_id,
        is_active=False,
    )
    db.add(version)
    db.flush()

    # Bump prompt updated_at — does not violate any trigger.
    prompt.updated_at = _utcnow()

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Edited",
        entity_type="PromptVersion",
        entity_id=version.version_id,
        detail=json.dumps({
            "prompt_id": prompt_id,
            "version_number": next_number,
            "change_summary": body.change_summary,
        }),
    ))

    db.commit()
    db.refresh(version)
    return PromptVersionOut.model_validate(version)


@router.get("", response_model=list[PromptVersionOut])
def list_versions(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_prompt(prompt_id, db)
    versions = (
        db.query(PromptVersion)
        .filter(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version_number.desc())
        .all()
    )
    return [PromptVersionOut.model_validate(v) for v in versions]


@router.get("/{version_id}", response_model=PromptVersionOut)
def get_version(
    prompt_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version_id == version_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return PromptVersionOut.model_validate(version)


@router.post("/{version_id}/activate", response_model=PromptVersionOut)
def activate_version(
    prompt_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = _get_prompt(prompt_id, db)
    if prompt.status == "Retired":
        raise HTTPException(status_code=409, detail="Cannot activate version on a Retired prompt")

    version = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.version_id == version_id,
        )
        .first()
    )
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    # Deactivate any currently-active version for this prompt.
    others = (
        db.query(PromptVersion)
        .filter(
            PromptVersion.prompt_id == prompt_id,
            PromptVersion.is_active == True,  # noqa: E712
            PromptVersion.version_id != version_id,
        )
        .all()
    )
    deactivated_ids = []
    for other in others:
        other.is_active = False
        deactivated_ids.append(other.version_id)

    # Flush deactivations first so the partial unique index
    # (one active version per prompt) is not momentarily violated.
    db.flush()

    now = _utcnow()
    version.is_active = True
    version.approved_by = current_user.user_id
    version.approved_at = now

    # If the prompt was Draft, activating its first version moves it to Active.
    prompt_status_changed = False
    if prompt.status == "Draft":
        prompt.status = "Active"
        prompt_status_changed = True
    prompt.updated_at = now

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="Approved",
        entity_type="PromptVersion",
        entity_id=version.version_id,
        detail=json.dumps({
            "prompt_id": prompt_id,
            "version_number": version.version_number,
            "deactivated": deactivated_ids,
        }),
    ))

    if prompt_status_changed:
        db.add(AuditLog(
            user_id=current_user.user_id,
            action="Activated",
            entity_type="Prompt",
            entity_id=prompt.prompt_id,
            detail=json.dumps({
                "from": "Draft",
                "to": "Active",
                "via_version_id": version.version_id,
            }),
        ))

    db.commit()
    db.refresh(version)
    return PromptVersionOut.model_validate(version)
