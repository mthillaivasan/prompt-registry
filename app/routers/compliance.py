"""Compliance check endpoints — submit, poll, list dimensions."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import AuditLog, ComplianceCheck, PromptVersion, ScoringDimension, User
from app.schemas import (
    AnomalyOut,
    ComplianceCheckOut,
    ComplianceCheckRequest,
    ComplianceJobOut,
    DimensionScoreOut,
    GoldStandardOut,
)
from services import compliance_engine
from services.guardrails import check_tier2_trigger

router = APIRouter(tags=["compliance"])


def _build_check_out(check: ComplianceCheck) -> ComplianceCheckOut:
    scores_parsed = json.loads(check.scores) if check.scores else {}
    scores_map = scores_parsed.get("scores", {})
    dimension_scores = [
        DimensionScoreOut(
            code=code,
            score=entry.get("score", 0) if isinstance(entry, dict) else 0,
            rationale=entry.get("rationale", "") if isinstance(entry, dict) else "",
        )
        for code, entry in scores_map.items()
    ]

    gold = None
    if check.gold_standard:
        gold_parsed = json.loads(check.gold_standard)
        gold = GoldStandardOut(**gold_parsed)

    anomaly = None
    if check.output_validation_result:
        anomaly_parsed = json.loads(check.output_validation_result)
        anomaly = AnomalyOut(**anomaly_parsed)

    flags = json.loads(check.flags) if check.flags else []

    return ComplianceCheckOut(
        check_id=check.check_id,
        version_id=check.version_id,
        run_at=check.run_at,
        run_by=check.run_by,
        overall_result=check.overall_result,
        blocking_defects=check.blocking_defects,
        gold_standard=gold,
        scores=dimension_scores,
        anomaly=anomaly,
        flags=flags,
    )


def _build_job_out(job, db: Session) -> ComplianceJobOut:
    result_out = None
    if job.result_id:
        check = db.query(ComplianceCheck).filter(ComplianceCheck.check_id == job.result_id).first()
        if check:
            result_out = _build_check_out(check)

    return ComplianceJobOut(
        job_id=job.job_id,
        version_id=job.version_id,
        requested_by=job.requested_by,
        requested_at=job.requested_at,
        status=job.status,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_message=job.error_message,
        force_refresh=job.force_refresh,
        result=result_out,
    )


@router.post("/compliance-checks", response_model=ComplianceJobOut, status_code=status.HTTP_202_ACCEPTED)
def request_compliance_check(
    body: ComplianceCheckRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = db.query(PromptVersion).filter(PromptVersion.version_id == body.version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    # Check cache
    if not body.force_refresh:
        cached = compliance_engine.get_cached_check(db, body.version_id)
        if cached:
            job = compliance_engine.create_job(
                db, body.version_id, current_user.user_id, body.force_refresh,
            )
            job.status = "Complete"
            job.result_id = cached.check_id
            db.commit()
            db.refresh(job)
            return _build_job_out(job, db)

    job = compliance_engine.create_job(
        db, body.version_id, current_user.user_id, body.force_refresh,
    )
    background_tasks.add_task(
        compliance_engine.run_compliance_check, db, job.job_id,
    )
    return _build_job_out(job, db)


@router.get("/compliance-checks/{job_id}", response_model=ComplianceJobOut)
def get_compliance_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = compliance_engine.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _build_job_out(job, db)


@router.get("/scoring-dimensions")
def list_dimensions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dims = compliance_engine.get_active_dimensions(db)
    return [
        {
            "dimension_id": d.dimension_id,
            "code": d.code,
            "name": d.name,
            "framework": d.framework,
            "scoring_type": d.scoring_type,
            "is_mandatory": d.is_mandatory,
            "blocking_threshold": d.blocking_threshold,
            "source_reference": d.source_reference,
            "description": d.description,
            "tier": d.tier,
            "tier2_trigger": d.tier2_trigger,
        }
        for d in dims
    ]


@router.get("/scoring-dimensions/applicable")
def get_applicable_dimensions(
    prompt_type: str = "",
    deployment_target: str = "",
    input_type: str = "",
    risk_tier: str = "",
    prompt_text_snippet: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        dims = compliance_engine.get_active_dimensions(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error loading dimensions: {str(e)}")

    tier1, tier2, tier3 = [], [], []

    for d in dims:
        dim_tier = getattr(d, 'tier', 3) or 3
        entry = {
            "code": d.code,
            "name": d.name,
            "framework": d.framework,
            "description": d.description,
            "scoring_type": d.scoring_type,
            "tier": dim_tier,
        }
        if dim_tier == 1:
            tier1.append(entry)
        elif dim_tier == 2:
            reason = check_tier2_trigger(d, deployment_target, input_type, risk_tier, prompt_text_snippet)
            entry["triggered"] = reason is not None
            entry["trigger_reason"] = reason or getattr(d, 'tier2_trigger', None) or ""
            tier2.append(entry)
        else:
            # Estimate score impact: removing one tier-3 dimension from the pool
            # reduces the gold standard by approximately weight/total * 100
            fw_weight = {"REGULATORY": 0.40, "OWASP": 0.30, "NIST": 0.20, "ISO42001": 0.10}
            fw_dims = [x for x in dims if x.framework == d.framework]
            w = fw_weight.get(d.framework, 0)
            impact = round((w / len(fw_dims)) * (4 / 4) * 100, 1) if fw_dims else 0
            entry["score_impact_if_removed"] = impact
            tier3.append(entry)

    return {"tier1": tier1, "tier2": tier2, "tier3": tier3}
