"""Import and upgrade endpoints — analyse, respond, apply, abandon."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    AuditLog,
    ComplianceCheckJob,
    Prompt,
    PromptVersion,
    UpgradeProposal,
    User,
)
from app.schemas import (
    AbandonRequest,
    AnalyseRequest,
    AnalyseResponse,
    ApplyRequest,
    ApplyResponse,
    FindingOut,
    ProposalOut,
    SuggestionOut,
    UserResponseOut,
    UserResponseRequest,
)
from services import upgrade_engine

router = APIRouter(tags=["upgrade"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _proposal_to_out(proposal: UpgradeProposal) -> ProposalOut:
    findings_raw = json.loads(proposal.findings) if proposal.findings else []
    suggestions_raw = json.loads(proposal.suggestions) if proposal.suggestions else []
    responses_raw = json.loads(proposal.user_responses) if proposal.user_responses else []

    findings = []
    for f in findings_raw:
        findings.append(FindingOut(
            finding_id=f.get("finding_id", ""),
            dimension_code=f.get("dimension_code", ""),
            dimension_name=f.get("dimension_name", ""),
            framework=f.get("framework", ""),
            current_score=f.get("current_score", 0),
            current_finding=f.get("current_finding", ""),
            severity=f.get("severity", ""),
            source_reference=f.get("source_reference", ""),
        ))

    suggestions = []
    for s in suggestions_raw:
        suggestions.append(SuggestionOut(
            suggestion_id=s.get("suggestion_id", ""),
            finding_id=s.get("finding_id"),
            dimension_code=s.get("dimension_code", ""),
            change_type=s.get("change_type", ""),
            description=s.get("description", ""),
            suggested_text=s.get("suggested_text", ""),
            rationale=s.get("rationale", ""),
            expected_score_improvement=s.get("expected_score_improvement"),
            insertion_hint=s.get("insertion_hint"),
        ))

    responses = [UserResponseOut(**r) for r in responses_raw]

    return ProposalOut(
        proposal_id=proposal.proposal_id,
        prompt_id=proposal.prompt_id,
        source_version_id=proposal.source_version_id,
        proposed_at=proposal.proposed_at,
        proposed_by=proposal.proposed_by,
        status=proposal.status,
        inferred_purpose=proposal.inferred_purpose,
        inferred_prompt_type=proposal.inferred_prompt_type,
        inferred_risk_tier=proposal.inferred_risk_tier,
        classification_confidence=proposal.classification_confidence,
        findings=findings,
        suggestions=suggestions,
        user_responses=responses,
        responses_recorded_at=proposal.responses_recorded_at,
        resulting_version_id=proposal.resulting_version_id,
        applied_at=proposal.applied_at,
        applied_by=proposal.applied_by,
        abandoned_reason=proposal.abandoned_reason,
    )


# ── POST /prompts/analyse ───────────────────────────────────────────────────

@router.post("/prompts/analyse", response_model=AnalyseResponse, status_code=status.HTTP_202_ACCEPTED)
def analyse_prompt(
    body: AnalyseRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = upgrade_engine.create_proposal(db, body.prompt_text, current_user.user_id)

    if body.prompt_id:
        proposal.prompt_id = body.prompt_id
    if body.source_version_id:
        proposal.source_version_id = body.source_version_id
    db.commit()

    # Create tracking job
    job = ComplianceCheckJob(
        version_id="pending-analysis",
        requested_by=current_user.user_id,
        status="Queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        _run_analysis_with_job, db, proposal.proposal_id, job.job_id,
        body.prompt_text, current_user.user_id,
    )

    return AnalyseResponse(
        proposal_id=proposal.proposal_id,
        job_id=job.job_id,
        status="Queued",
    )


def _run_analysis_with_job(db: Session, proposal_id: str, job_id: str, prompt_text: str, user_id: str) -> None:
    job = db.query(ComplianceCheckJob).filter(ComplianceCheckJob.job_id == job_id).first()
    if job:
        job.status = "Running"
        job.started_at = _utcnow()
        db.commit()

    try:
        upgrade_engine.run_analysis(db, proposal_id, prompt_text, user_id)
        if job:
            proposal = upgrade_engine.get_proposal(db, proposal_id)
            job.status = "Failed" if proposal and proposal.status == "Failed" else "Complete"
            job.completed_at = _utcnow()
            db.commit()
    except Exception as e:
        if job:
            job.status = "Failed"
            job.error_message = str(e)
            job.completed_at = _utcnow()
            db.commit()


# ── GET /proposals/{id} ─────────────────────────────────────────────────────

@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _proposal_to_out(proposal)


# ── POST /proposals/{id}/responses ───────────────────────────────────────────

@router.post("/proposals/{proposal_id}/responses", response_model=ProposalOut)
def record_response(
    proposal_id: str,
    body: UserResponseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status in ("Applied", "Abandoned"):
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status}")

    try:
        proposal = upgrade_engine.record_response(
            db, proposal,
            suggestion_id=body.suggestion_id,
            response=body.response,
            user_id=current_user.user_id,
            modified_text=body.modified_text,
            user_note=body.user_note,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _proposal_to_out(proposal)


# ── POST /proposals/{id}/apply ───────────────────────────────────────────────

@router.post("/proposals/{proposal_id}/apply", response_model=ApplyResponse)
def apply_proposal(
    proposal_id: str,
    body: ApplyRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status == "Applied":
        raise HTTPException(status_code=409, detail="Proposal already applied")
    if proposal.status == "Abandoned":
        raise HTTPException(status_code=409, detail="Proposal was abandoned")

    missing = upgrade_engine.validate_all_responses(proposal)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing responses for suggestions: {missing}",
        )

    prompt_id = body.prompt_id if body else None

    try:
        version, compliance_job_id = upgrade_engine.apply_proposal(
            db, proposal, current_user.user_id, prompt_id=prompt_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ApplyResponse(version_id=version.version_id, compliance_job_id=compliance_job_id)


# ── POST /proposals/{id}/abandon ─────────────────────────────────────────────

@router.post("/proposals/{proposal_id}/abandon", response_model=ProposalOut)
def abandon_proposal(
    proposal_id: str,
    body: AbandonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.status == "Applied":
        raise HTTPException(status_code=409, detail="Proposal already applied")

    proposal = upgrade_engine.abandon_proposal(db, proposal, body.reason, current_user.user_id)
    return _proposal_to_out(proposal)


# ── GET /prompts/{id}/proposals ──────────────────────────────────────────────

@router.get("/prompts/{prompt_id}/proposals", response_model=list[ProposalOut])
def list_proposals(
    prompt_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prompt = db.query(Prompt).filter(Prompt.prompt_id == prompt_id).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    proposals = upgrade_engine.get_proposals_for_prompt(db, prompt_id)
    return [_proposal_to_out(p) for p in proposals]
