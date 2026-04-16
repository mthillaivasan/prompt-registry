import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import compliance_engine, schemas, upgrade_engine
from app.database import get_db
from app.models import (
    AuditLog,
    ComplianceCheckJob,
    ComplianceResult,
    Prompt,
    PromptVersion,
    UpgradeProposal,
)

router = APIRouter(tags=["upgrade"])


def _proposal_to_out(proposal: UpgradeProposal) -> schemas.ProposalOut:
    findings = json.loads(proposal.findings_json) if proposal.findings_json else []
    suggestions = json.loads(proposal.suggestions_json) if proposal.suggestions_json else []
    user_responses = json.loads(proposal.user_responses_json) if proposal.user_responses_json else []

    return schemas.ProposalOut(
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
        findings=[schemas.FindingOut(**f) for f in findings],
        suggestions=[schemas.SuggestionOut(**s) for s in suggestions],
        user_responses=[schemas.UserResponseOut(**r) for r in user_responses],
        responses_recorded_at=proposal.responses_recorded_at,
        resulting_version_id=proposal.resulting_version_id,
        applied_at=proposal.applied_at,
        applied_by=proposal.applied_by,
        abandoned_reason=proposal.abandoned_reason,
    )


# --- POST /prompts/analyse ---

@router.post("/prompts/analyse", response_model=schemas.AnalyseResponse, status_code=202)
def analyse_prompt(
    body: schemas.AnalyseRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Create proposal record
    proposal = upgrade_engine.create_proposal(db, body.prompt_text, body.prompt_name)

    # Write AuditLog: PromptImported BEFORE queuing the analysis job
    upgrade_engine._write_audit_log(
        db, "PromptImported", "UpgradeProposal", proposal.proposal_id,
        detail=f"Prompt text submitted for analysis. Length: {len(body.prompt_text)} chars.",
    )

    # Create a tracking job
    job = ComplianceCheckJob(
        version_id=0,  # no version yet — this is an analysis job
        requested_by="SYSTEM",
        status="Queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue async analysis
    background_tasks.add_task(
        _run_analysis_with_job, db, proposal.proposal_id, job.job_id,
    )

    return schemas.AnalyseResponse(
        proposal_id=proposal.proposal_id,
        job_id=job.job_id,
        status="Queued",
    )


def _run_analysis_with_job(db: Session, proposal_id: str, job_id: str) -> None:
    """Wrapper that updates job status around the analysis."""
    from app.models import ComplianceCheckJob
    import datetime

    stmt = select(ComplianceCheckJob).where(ComplianceCheckJob.job_id == job_id)
    job = db.scalars(stmt).first()
    if job:
        job.status = "Running"
        job.started_at = datetime.datetime.utcnow()
        db.commit()

    upgrade_engine.run_analysis(db, proposal_id)

    if job:
        proposal = upgrade_engine.get_proposal(db, proposal_id)
        if proposal and proposal.status == "Failed":
            job.status = "Failed"
            job.error_message = "Analysis failed"
        else:
            job.status = "Complete"
        job.completed_at = datetime.datetime.utcnow()
        db.commit()


# --- GET /proposals/{id} ---

@router.get("/proposals/{proposal_id}", response_model=schemas.ProposalOut)
def get_proposal(proposal_id: str, db: Session = Depends(get_db)):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _proposal_to_out(proposal)


# --- POST /proposals/{id}/responses ---

@router.post("/proposals/{proposal_id}/responses", response_model=schemas.ProposalOut)
def record_response(
    proposal_id: str,
    body: schemas.UserResponseRequest,
    db: Session = Depends(get_db),
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
            modified_text=body.modified_text,
            user_note=body.user_note,
            responded_by=body.responded_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return _proposal_to_out(proposal)


# --- POST /proposals/{id}/apply ---

@router.post("/proposals/{proposal_id}/apply", response_model=schemas.ApplyResponse)
def apply_proposal(
    proposal_id: str,
    db: Session = Depends(get_db),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status == "Applied":
        raise HTTPException(status_code=409, detail="Proposal already applied")
    if proposal.status == "Abandoned":
        raise HTTPException(status_code=409, detail="Proposal was abandoned")

    # Validate ALL suggestions have a user_response — 422 if any missing
    missing = upgrade_engine.validate_all_responses(proposal)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing responses for suggestions: {missing}",
        )

    new_version, compliance_job_id = upgrade_engine.apply_proposal(
        db, proposal, applied_by="user",
    )

    return schemas.ApplyResponse(
        version_id=new_version.id,
        compliance_job_id=compliance_job_id,
    )


# --- POST /proposals/{id}/abandon ---

@router.post("/proposals/{proposal_id}/abandon", response_model=schemas.ProposalOut)
def abandon_proposal(
    proposal_id: str,
    body: schemas.AbandonRequest,
    db: Session = Depends(get_db),
):
    proposal = upgrade_engine.get_proposal(db, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")

    if proposal.status == "Applied":
        raise HTTPException(status_code=409, detail="Proposal already applied")

    proposal = upgrade_engine.abandon_proposal(db, proposal, body.reason)
    return _proposal_to_out(proposal)


# --- GET /prompts/{id}/proposals ---

@router.get("/prompts/{prompt_id}/proposals", response_model=list[schemas.ProposalOut])
def list_proposals(prompt_id: int, db: Session = Depends(get_db)):
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    proposals = upgrade_engine.get_proposals_for_prompt(db, prompt_id)
    return [_proposal_to_out(p) for p in proposals]


# --- GET /prompts/{id}/timeline ---

@router.get("/prompts/{prompt_id}/timeline", response_model=list[schemas.VersionTimelineEntry])
def get_timeline(prompt_id: int, db: Session = Depends(get_db)):
    prompt = db.get(Prompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    stmt = (
        select(PromptVersion)
        .where(PromptVersion.prompt_id == prompt_id)
        .order_by(PromptVersion.version.desc())
    )
    versions = list(db.scalars(stmt).all())

    latest_version = versions[0].version if versions else 0
    timeline = []

    for v in versions:
        # Check if this version was an upgrade
        was_upgrade = v.upgrade_proposal_id is not None

        # Get compliance result for this version
        result_stmt = (
            select(ComplianceResult)
            .where(ComplianceResult.version_id == v.id)
            .order_by(ComplianceResult.created_at.desc())
        )
        compliance_result = db.scalars(result_stmt).first()

        overall_result = None
        gold_grade = None
        defects = []
        total_defects = 0
        open_defects = 0

        if compliance_result:
            overall_result = "Blocked" if compliance_result.blocked else "Passed"
            gold_grade = compliance_result.gold_score
            scores_parsed = json.loads(compliance_result.scores_json)
            scores_map = scores_parsed.get("scores", {})

            dims = compliance_engine._get_active_dimensions(db)
            dim_lookup = {d.code: d for d in dims}

            for code, entry in scores_map.items():
                if isinstance(entry, dict) and entry.get("score", 5) < 4:
                    dim = dim_lookup.get(code)
                    total_defects += 1
                    # Open if blocking and score <= threshold
                    if dim and dim.blocking_threshold and entry.get("score", 5) <= dim.blocking_threshold:
                        open_defects += 1
                    defects.append(schemas.FindingOut(
                        finding_id="",
                        dimension_code=code,
                        dimension_name=dim.name if dim else code,
                        framework=dim.framework if dim else "",
                        current_score=entry.get("score", 0),
                        current_finding=entry.get("rationale", ""),
                        severity="Blocking" if dim and dim.blocking_threshold and entry.get("score", 5) <= dim.blocking_threshold else "Advisory",
                        source_reference=dim.description if dim else "",
                    ))

        timeline.append(schemas.VersionTimelineEntry(
            version_number=v.version,
            created_at=v.created_at,
            created_by="upgrade" if was_upgrade else "manual",
            change_summary=v.change_note or "",
            is_active=v.version == latest_version,
            overall_result=overall_result,
            gold_standard_grade=gold_grade,
            open_defects=open_defects,
            total_defects=total_defects,
            was_upgrade=was_upgrade,
            defects=defects,
        ))

    return timeline


# --- GET /audit-log ---

@router.get("/audit-log")
def list_audit_log(
    skip: int = 0,
    limit: int = 50,
    action: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    stmt = stmt.offset(skip).limit(limit)
    entries = list(db.scalars(stmt).all())
    return [
        {
            "id": e.id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "actor": e.actor,
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
