"""Compliance check endpoints — submit, poll, list dimensions.

Block 10 of the refactor adds standards-labelled output. The
/compliance-checks responses now carry standard_code and clause for
each scored dimension, joined from the new dimensions and standards
tables when the new catalogue has the dimension. Legacy ScoringDimension
records (which the engine still scores against during the dual-write
window) are labelled by their `framework` column for continuity.

A new endpoint /phase-dimensions/{phase_code} returns the new-shape
dimension catalogue with full standard labelling. UI consumers should
move to this endpoint when ready; /scoring-dimensions remains for
backward compatibility.
"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    AuditLog,
    ComplianceCheck,
    Dimension,
    PromptVersion,
    ScoringDimension,
    Standard,
    User,
)
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


# ── Standards labelling helpers (Block 10) ──────────────────────────────────

# Maps the legacy `framework` column to a (standard_code, default_clause)
# pair so legacy ScoringDimension records can be displayed with the same
# standards-labelled shape as new Dimension records. The mapping lives in
# this single adapter module — the engine and the new tables do not use it.
_LEGACY_FRAMEWORK_LABELS = {
    "REGULATORY": ("EU_AI_ACT", "General"),
    "OWASP": ("OWASP_LLM_TOP10", "LLM Top 10"),
    "NIST": ("NIST_AI_RMF", "Core function"),
    "ISO42001": ("ISO_42001", "Annex A"),
}


def _standard_for_legacy_framework(db: Session, framework: str) -> dict:
    """Return {standard_code, title, version, clause} for a legacy framework
    name. If the standards catalogue is not seeded, returns a minimal
    fallback shape."""
    code, default_clause = _LEGACY_FRAMEWORK_LABELS.get(
        framework, (framework, "")
    )
    s = db.query(Standard).filter(Standard.standard_code == code).one_or_none()
    if s is None:
        return {
            "standard_code": code,
            "title": framework,
            "version": "",
            "clause": default_clause,
        }
    return {
        "standard_code": s.standard_code,
        "title": s.title,
        "version": s.version,
        "clause": default_clause,
    }


def _standard_for_dimension_code(db: Session, code: str) -> dict | None:
    """Look up the standard label for a new-shape dimension code. Returns
    None if the code isn't in the new catalogue."""
    d = db.query(Dimension).filter(Dimension.code == code).one_or_none()
    if d is None:
        return None
    s = db.query(Standard).filter(Standard.standard_id == d.standard_id).one_or_none()
    if s is None:
        return None
    return {
        "standard_code": s.standard_code,
        "title": s.title,
        "version": s.version,
        "clause": d.clause or "",
    }


def _build_check_out(check: ComplianceCheck, db: Session | None = None) -> ComplianceCheckOut:
    scores_parsed = json.loads(check.scores) if check.scores else {}
    scores_map = scores_parsed.get("scores", {})

    # Build a label map: dimension code -> {standard_code, title, version, clause}.
    # Prefer the new Dimension catalogue. Fall back to the legacy
    # ScoringDimension's framework column for legacy code ranges.
    label_map: dict[str, dict] = {}
    if db is not None:
        for code in scores_map.keys():
            new_label = _standard_for_dimension_code(db, code)
            if new_label is not None:
                label_map[code] = new_label
                continue
            legacy = (
                db.query(ScoringDimension)
                .filter(ScoringDimension.code == code)
                .one_or_none()
            )
            if legacy is not None:
                label_map[code] = _standard_for_legacy_framework(db, legacy.framework)

    dimension_scores = [
        DimensionScoreOut(
            code=code,
            score=entry.get("score", 0) if isinstance(entry, dict) else 0,
            rationale=entry.get("rationale", "") if isinstance(entry, dict) else "",
            standard=label_map.get(code),
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
            result_out = _build_check_out(check, db)

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


@router.get("/scoring-dimensions/wrapper-metadata")
def list_wrapper_metadata_dimensions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return active scoring_dimensions whose content_type is wrapper_metadata.

    Surfaces governance context that lives around the LLM output rather than
    inside the prompt body. Consumed by the prompt-detail Governance Context
    panel. Read-only catalogue view; per-prompt assignments (accountable
    reviewer, audit-trail format, etc.) are a follow-on per PHASE2.md.
    """
    rows = (
        db.query(ScoringDimension)
        .filter(
            ScoringDimension.is_active == True,  # noqa: E712
            ScoringDimension.content_type == "wrapper_metadata",
        )
        .order_by(ScoringDimension.sort_order)
        .all()
    )
    return [
        {
            "code": d.code,
            "name": d.name,
            "framework": d.framework,
            "source_reference": d.source_reference,
            "description": d.description,
            "score_5_criteria": d.score_5_criteria,
        }
        for d in rows
    ]


@router.get("/phase-dimensions/{phase_code}")
def list_phase_dimensions(
    phase_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List dimensions for a phase with full standards labelling.

    Returns rows from the new `dimensions` table joined to `standards`.
    Replaces the legacy /scoring-dimensions endpoint for new UI consumers.
    """
    dims = compliance_engine.get_phase_dimensions(db, phase_code)
    if not dims:
        return []
    standard_ids = {d.standard_id for d in dims}
    standards = (
        db.query(Standard).filter(Standard.standard_id.in_(standard_ids)).all()
    )
    standards_by_id = {s.standard_id: s for s in standards}

    result = []
    for d in dims:
        s = standards_by_id.get(d.standard_id)
        result.append({
            "dimension_id": d.dimension_id,
            "code": d.code,
            "title": d.title,
            "phase_code": phase_code,
            "standard": {
                "standard_code": s.standard_code if s else "",
                "title": s.title if s else "",
                "version": s.version if s else "",
                "clause": d.clause or "",
            },
            "scoring_type": d.scoring_type,
            "is_mandatory": d.is_mandatory,
            "blocking_threshold": d.blocking_threshold,
            "content_type": d.content_type,
            "applicability": json.loads(d.applicability),
            "instructional_text": d.instructional_text,
        })
    return result


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
