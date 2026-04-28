"""Brief CRUD endpoints — create, update, list, get, abandon, complete."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Brief, PromptLibrary, User
from app.schemas import BriefCreate, BriefOut, BriefUpdate, PromptType
from services.library_excerpt import extract_topic_excerpt
from services.library_matching import match_library

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
        interviewer_id=current_user.user_id,
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
    try:
        briefs = query.order_by(Brief.updated_at.desc()).all()
        return [BriefOut.model_validate(b) for b in briefs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


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


def _approved_ids(brief: Brief) -> list[str]:
    try:
        return json.loads(brief.approved_library_refs or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def _brief_topic_signal(brief: Brief) -> tuple[str | None, str | None, list[str]]:
    """Derive the matching context (prompt_type, domain, topic_coverage signal)
    from a brief's stored step_answers + metadata.

    prompt_type: from topic_1_prompt_type pick. Multi-select rule: prefer
    "Extraction" if present, else first picked, else None.

    domain: derived from whether the brief carries a client_name. A
    populated client_name implies a regulated-finance use case in this
    registry, so finance-tagged library entries get the domain bonus.
    Empty client_name leaves domain unset (no bonus, no penalty).

    topic_coverage signal: every prose topic with a non-red state in
    step_answers. The signal answers "what topics has the user already
    thought about?" — library entries that have *also* worked through
    those topics rank highest.
    """
    try:
        answers = json.loads(brief.step_answers or "{}")
    except (json.JSONDecodeError, TypeError):
        answers = {}

    prompt_type = None
    pt_entry = answers.get("topic_1_prompt_type")
    if isinstance(pt_entry, dict):
        v = pt_entry.get("value")
        picks = v if isinstance(v, list) else ([v] if v else [])
        if picks:
            prompt_type = "Extraction" if "Extraction" in picks else picks[0]

    domain = "finance" if (brief.client_name or "").strip() else None

    topic_signal: list[str] = []
    for key, entry in answers.items():
        if not key.startswith("topic_"):
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("state") in ("amber", "green"):
            topic_signal.append(key)

    return prompt_type, domain, topic_signal


@router.get("/{brief_id}/library-matches")
def list_library_matches(
    brief_id: str,
    limit: int = Query(3, ge=0, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return ranked library candidates for this brief's context.

    The Brief Builder UI surfaces these as suggested references. Each
    payload carries `approved` so the panel can show which ones the user
    has already opted into. Approval is persisted via PATCH /briefs/{id}
    with `approved_library_refs`; see the L2 design rule that user
    approval gates downstream consumption.
    """
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    prompt_type, domain, topic_signal = _brief_topic_signal(brief)
    if not prompt_type:
        # No prompt_type picked yet — no matches to surface. Empty list keeps
        # the UI's "no references found" path uniform with the genuinely-empty
        # case (library has no Extraction entries, etc.).
        return []

    approved = set(_approved_ids(brief))
    matches = match_library(
        db,
        prompt_type=prompt_type,
        domain=domain,
        topic_coverage=topic_signal,
        limit=limit,
    )
    return [
        {
            "library_id": entry.library_id,
            "title": entry.title,
            "summary": entry.summary,
            "source_provenance": entry.source_provenance,
            "domain": entry.domain,
            "topic_coverage": _safe_topic_coverage(entry),
            "score": score,
            "approved": entry.library_id in approved,
        }
        for entry, score in matches
    ]


def _safe_topic_coverage(entry: PromptLibrary) -> list[str]:
    try:
        return json.loads(entry.topic_coverage or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


@router.get("/{brief_id}/library-references")
def list_library_references(
    brief_id: str,
    topic_id: str | None = Query(None, min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return user-approved library references for downstream consumption.

    Two shapes depending on `topic_id`:

      - With topic_id: returns excerpts matching that topic (drives
        validate-topic few-shot context). Entries whose excerpt extractor
        returns None — i.e. the entry's full_text doesn't address the
        topic — are dropped, mirroring /library/relevant.

      - Without topic_id: returns each approved entry's title, summary,
        and full_text (drives generator structural-reference context).

    Authorisation: any authenticated user. Same posture as
    /library/relevant — Makers building briefs are the primary
    consumers and the data is reference content, not sensitive.
    """
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    approved = _approved_ids(brief)
    if not approved:
        return []

    entries = (
        db.query(PromptLibrary)
        .filter(PromptLibrary.library_id.in_(approved))
        .all()
    )
    # Preserve approval-list order so the UI can show "first approved
    # surfaces first" if it wants ordering control.
    by_id = {e.library_id: e for e in entries}
    ordered = [by_id[i] for i in approved if i in by_id]

    if topic_id:
        out = []
        for e in ordered:
            excerpt = extract_topic_excerpt(e.full_text, topic_id)
            if not excerpt:
                continue
            out.append({
                "library_id": e.library_id,
                "title": e.title,
                "source_provenance": e.source_provenance,
                "excerpt": excerpt,
            })
        return out

    return [
        {
            "library_id": e.library_id,
            "title": e.title,
            "summary": e.summary,
            "source_provenance": e.source_provenance,
            "full_text": e.full_text,
        }
        for e in ordered
    ]


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

    if body.title is not None:
        brief.title = body.title
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
    if body.approved_library_refs is not None:
        brief.approved_library_refs = json.dumps(body.approved_library_refs)

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


@router.patch("/{brief_id}/step/{step_num}", response_model=BriefOut)
def save_step(
    brief_id: str,
    step_num: int,
    body: BriefUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    if brief.status not in ("In Progress",):
        raise HTTPException(status_code=409, detail="Brief is finalised")

    if body.title is not None:
        brief.title = body.title
    if body.step_answers is not None:
        existing = json.loads(brief.step_answers or "{}")
        existing.update(body.step_answers)
        brief.step_answers = json.dumps(existing)
    if body.quality_score is not None:
        brief.quality_score = body.quality_score
    if body.selected_guardrails is not None:
        brief.selected_guardrails = json.dumps(body.selected_guardrails)
    if body.client_name is not None:
        brief.client_name = body.client_name
    if body.business_owner_name is not None:
        brief.business_owner_name = body.business_owner_name
    if body.business_owner_role is not None:
        brief.business_owner_role = body.business_owner_role
    if body.approved_library_refs is not None:
        brief.approved_library_refs = json.dumps(body.approved_library_refs)

    brief.step_progress = max(brief.step_progress, step_num)
    brief.updated_at = _utcnow()
    db.commit()
    db.refresh(brief)
    return BriefOut.model_validate(brief)


@router.post("/{brief_id}/skip-step/{step_num}")
def skip_step(
    brief_id: str,
    step_num: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    step_names = {2: "Input type", 3: "Output type", 4: "Audience", 5: "Constraints"}
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefStepSkipped",
        entity_type="Brief",
        entity_id=brief.brief_id,
        detail=json.dumps({"step": step_num, "step_name": step_names.get(step_num, f"Step {step_num}")}),
    ))
    db.commit()
    return {"ok": True}


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


@router.delete("/{brief_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_brief(
    brief_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete a brief.

    Authorisation:
      - Maker: may delete own brief iff status == "In Progress" (drafts only).
      - Checker / Admin: may delete any brief regardless of owner or status.

    Hard delete, not soft: no table references Brief as an FK source, and
    AuditLog.entity_id is a plain string so the audit record survives the
    row's removal. The BriefDeleted audit entry is written before the
    db.delete() so the trail captures title + prior status at the moment
    of removal.
    """
    brief = db.query(Brief).filter(Brief.brief_id == brief_id).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    role = current_user.role
    is_owner = brief.brief_builder_id == current_user.user_id
    if role == "Maker":
        if not is_owner:
            raise HTTPException(status_code=403, detail="Maker may only delete own briefs")
        if brief.status != "In Progress":
            raise HTTPException(status_code=403, detail="Maker may only delete draft briefs")
    elif role not in ("Checker", "Admin"):
        raise HTTPException(status_code=403, detail="Role not permitted to delete briefs")

    db.add(AuditLog(
        user_id=current_user.user_id,
        action="BriefDeleted",
        entity_type="Brief",
        entity_id=brief.brief_id,
        detail=json.dumps({"title": brief.title, "prior_status": brief.status}),
    ))
    db.delete(brief)
    db.commit()


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
