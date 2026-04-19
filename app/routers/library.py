"""Prompt library admin endpoints — Admin-only CRUD over the reference library.

Library entries are high-quality example prompts surfaced in Brief Builder
coaching (Drop L2) and used as few-shot context for validate-topic. Distinct
from prompt_templates (those feed the generator).

All mutations require Admin role. Reads also require Admin for MVP — if
Brief Builder integration needs broader read access later, relax GET only.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import PromptLibrary, User
from app.schemas import (
    PromptLibraryCreate,
    PromptLibraryListOut,
    PromptLibraryOut,
    PromptLibraryUpdate,
    PromptType,
)
from services.library_excerpt import extract_topic_excerpt

router = APIRouter(prefix="/library", tags=["library"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_admin(user: User) -> None:
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin role required")


@router.get("", response_model=PromptLibraryListOut)
def list_library(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    prompt_type: str | None = Query(None),
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)

    query = db.query(PromptLibrary)
    if prompt_type:
        query = query.filter(PromptLibrary.prompt_type == prompt_type)
    if domain:
        query = query.filter(PromptLibrary.domain == domain)

    total = query.count()
    items = (
        query.order_by(PromptLibrary.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [PromptLibraryOut.model_validate(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (page * page_size) < total,
    }


@router.get("/relevant")
def relevant_library_entries(
    prompt_type: PromptType,
    topic_id: str = Query(..., min_length=1),
    limit: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return library entries relevant to the focal topic for few-shot
    coaching context and "See reference" affordances in Brief Builder.

    Any authenticated user may read this. No Admin gate — Makers building
    briefs are the primary consumers. Entries whose topic_coverage contains
    the focal topic_id rank first; within each band, newest first. Per-topic
    excerpt is computed at request time via services.library_excerpt; entries
    where the extractor returns None are dropped so the UI never sees empty
    excerpt strings.
    """
    candidates = (
        db.query(PromptLibrary)
        .filter(PromptLibrary.prompt_type == prompt_type)
        .order_by(PromptLibrary.created_at.desc())
        .all()
    )

    scored: list[tuple[int, dict]] = []
    for c in candidates:
        excerpt = extract_topic_excerpt(c.full_text, topic_id)
        if not excerpt:
            continue
        try:
            coverage = json.loads(c.topic_coverage or "[]")
        except (json.JSONDecodeError, TypeError):
            coverage = []
        topic_rank = 0 if topic_id in coverage else 1
        scored.append((topic_rank, {
            "library_id": c.library_id,
            "title": c.title,
            "source_provenance": c.source_provenance,
            "excerpt": excerpt,
        }))

    scored.sort(key=lambda pair: pair[0])
    return [payload for _, payload in scored[:limit]]


@router.get("/{library_id}", response_model=PromptLibraryOut)
def get_library_entry(
    library_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    entry = db.query(PromptLibrary).filter(PromptLibrary.library_id == library_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")
    return PromptLibraryOut.model_validate(entry)


@router.post("", response_model=PromptLibraryOut, status_code=status.HTTP_201_CREATED)
def create_library_entry(
    body: PromptLibraryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    existing = db.query(PromptLibrary).filter(PromptLibrary.title == body.title).first()
    if existing:
        raise HTTPException(status_code=409, detail="Library entry with this title already exists")

    now = _utcnow()
    entry = PromptLibrary(
        title=body.title,
        full_text=body.full_text,
        summary=body.summary,
        prompt_type=body.prompt_type,
        input_type=body.input_type,
        output_type=body.output_type,
        domain=body.domain,
        source_provenance=body.source_provenance,
        topic_coverage=json.dumps(body.topic_coverage or []),
        classification_notes=body.classification_notes,
        created_at=now,
        updated_at=now,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return PromptLibraryOut.model_validate(entry)


@router.patch("/{library_id}", response_model=PromptLibraryOut)
def update_library_entry(
    library_id: str,
    body: PromptLibraryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    entry = db.query(PromptLibrary).filter(PromptLibrary.library_id == library_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")

    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] != entry.title:
        clash = db.query(PromptLibrary).filter(PromptLibrary.title == data["title"]).first()
        if clash:
            raise HTTPException(status_code=409, detail="Another entry already uses that title")

    for field, value in data.items():
        if field == "topic_coverage":
            entry.topic_coverage = json.dumps(value or [])
        else:
            setattr(entry, field, value)

    entry.updated_at = _utcnow()
    db.commit()
    db.refresh(entry)
    return PromptLibraryOut.model_validate(entry)


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library_entry(
    library_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    entry = db.query(PromptLibrary).filter(PromptLibrary.library_id == library_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Library entry not found")
    db.delete(entry)
    db.commit()
