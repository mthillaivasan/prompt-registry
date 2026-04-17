"""Prompt CRUD endpoints — create, list, get, update, generate."""

import json
import os
from datetime import datetime, timezone

import anthropic
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, Prompt, PromptVersion, ScoringDimension, User
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    PromptCreate,
    PromptDetail,
    PromptOut,
    PromptUpdate,
    PromptVersionOut,
    ValidateBriefRequest,
    ValidateBriefResponse,
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
        deployment_target=body.deployment_target,
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
    prompts = query.order_by(Prompt.updated_at.desc()).all()
    return [PromptOut.model_validate(p) for p in prompts]


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


# ── Validate brief description via Claude ────────────────────────────────────

_VALIDATE_BRIEF_PROMPT = """\
You are reviewing a brief for an AI prompt about to be built for a regulated \
financial services firm.

The user has provided this description of the prompt's purpose:
"{user_input}"

Assess whether this description is specific enough to generate a high quality \
governed prompt. It must clearly state:
1. What the AI will process (the input)
2. What the AI will produce (the output)
3. What the human does with the result

If all three are clear — respond with: ACCEPTED
If any are missing or vague — respond with: QUESTION: [one specific \
follow-up question that addresses the most important gap]

Do not ask more than one question at a time.
Do not accept vague descriptions like "process documents" or "help with compliance"."""


@router.post("/validate-brief", response_model=ValidateBriefResponse)
def validate_brief(
    body: ValidateBriefRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt_text = _VALIDATE_BRIEF_PROMPT.replace("{user_input}", body.description)
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=256,
            messages=[{"role": "user", "content": prompt_text}],
        )
        result = response.content[0].text.strip()
        if result.startswith("ACCEPTED"):
            return ValidateBriefResponse(accepted=True, question=None)
        elif result.startswith("QUESTION:"):
            question = result[len("QUESTION:"):].strip()
            return ValidateBriefResponse(accepted=False, question=question)
        else:
            return ValidateBriefResponse(accepted=False, question=result)
    except Exception as e:
        return ValidateBriefResponse(accepted=True, question=None)


# ── Generate prompt text via Claude ──────────────────────────────────────────

_GENERATE_SYSTEM_PROMPT_TEMPLATE = """\
You are an expert prompt engineer for regulated financial services. \
Generate a production-ready system prompt based on the brief below. \
The prompt must include guardrail instructions for EACH of the \
following dimensions — and ONLY these dimensions. Do not add \
guardrails for dimensions not listed.

REQUIRED GUARDRAIL DIMENSIONS:
{guardrail_block}

Write the prompt in second person addressing the AI model. \
End with a section titled TONE AND BEHAVIOUR RULES containing all guardrails.
Return only the prompt text — no explanation, no preamble."""


def _resolve_guardrails(body, db) -> list:
    """Determine which dimensions to include in the generated prompt."""
    from app.routers.compliance import _check_tier2_trigger
    dims = (
        db.query(ScoringDimension)
        .filter(ScoringDimension.is_active == True)  # noqa: E712
        .order_by(ScoringDimension.sort_order)
        .all()
    )

    if body.selected_guardrails:
        codes = set(body.selected_guardrails)
        return [d for d in dims if d.code in codes]

    # Auto-detect: tier1 always + triggered tier2 + all tier3
    selected = []
    for d in dims:
        if d.tier == 1:
            selected.append(d)
        elif d.tier == 2:
            reason = _check_tier2_trigger(d, body.deployment_target, body.input_type, "", body.brief_text)
            if reason:
                selected.append(d)
        else:
            selected.append(d)
    return selected


@router.post("/generate", response_model=GenerateResponse)
def generate_prompt_text(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from services.injection_scanner import scan as injection_scan

    if body.brief_text:
        scan_result = injection_scan("brief_text", body.brief_text, db)
        if scan_result["result"] == "critical":
            db.add(AuditLog(
                user_id=current_user.user_id,
                action="InjectionDetected",
                entity_type="Prompt",
                entity_id="generate",
                detail=json.dumps({"scan_result": scan_result}),
            ))
            db.commit()
            raise HTTPException(
                status_code=400,
                detail=f"Injection detected in brief text: {scan_result['message']}",
            )

    selected_dims = _resolve_guardrails(body, db)
    guardrail_block = "\n".join(
        f"- {d.code} ({d.name}): {d.description}" for d in selected_dims
    )
    system_prompt = _GENERATE_SYSTEM_PROMPT_TEMPLATE.replace("{guardrail_block}", guardrail_block)

    brief_parts = [f"Title: {body.title}", f"Prompt type: {body.prompt_type}"]
    if body.deployment_target:
        brief_parts.append(f"Deployment target: {body.deployment_target}")
    if body.input_type:
        brief_parts.append(f"Input type: {body.input_type}")
    if body.output_type:
        brief_parts.append(f"Output type: {body.output_type}")
    if body.brief_text:
        brief_parts.append(f"Additional brief:\n{body.brief_text}")

    user_message = "BRIEF:\n" + "\n".join(brief_parts) + "\n\nGenerate the prompt now."

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        generated = response.content[0].text.strip()
        if generated.startswith("```"):
            lines = generated.split("\n")
            generated = "\n".join(lines[1:-1])

        db.add(AuditLog(
            user_id=current_user.user_id,
            action="PromptGenerated",
            entity_type="Prompt",
            entity_id="generate",
            detail=json.dumps({
                "title": body.title,
                "prompt_type": body.prompt_type,
                "selected_guardrails": [d.code for d in selected_dims],
                "generated_length": len(generated),
            }),
        ))
        db.commit()

        return GenerateResponse(prompt_text=generated)
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=502, detail="Anthropic API key is invalid or missing")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Claude API error: {str(e)}")
