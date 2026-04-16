import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app import compliance_engine, schemas
from app.database import get_db
from app.models import ComplianceCheckJob, ScoringDimension

router = APIRouter(tags=["compliance"])


# --- Scoring Dimensions ---

@router.get("/scoring-dimensions", response_model=list[schemas.ScoringDimensionOut])
def list_dimensions(db: Session = Depends(get_db)):
    dims = compliance_engine._get_active_dimensions(db)
    return [schemas.ScoringDimensionOut.model_validate(d) for d in dims]


# --- Compliance Jobs ---

@router.post("/compliance-checks", response_model=schemas.ComplianceJobOut, status_code=202)
def request_compliance_check(
    body: schemas.ComplianceCheckRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    # Validate version exists
    from app.models import PromptVersion
    version = db.get(PromptVersion, body.version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    # Check cache unless force_refresh
    if not body.force_refresh:
        cached = compliance_engine.get_cached_result(db, body.version_id)
        if cached:
            # Create a job that immediately points to cached result
            job = compliance_engine.create_job(
                db, body.version_id, body.requested_by, body.force_refresh
            )
            job.status = "Complete"
            job.result_id = cached.id
            db.commit()
            db.refresh(job)
            return _job_to_out(job, db)

    # Create job and run in background
    job = compliance_engine.create_job(
        db, body.version_id, body.requested_by, body.force_refresh
    )
    background_tasks.add_task(
        compliance_engine.run_compliance_check, db, job.job_id
    )
    return _job_to_out(job, db)


@router.get("/compliance-jobs/{job_id}", response_model=schemas.ComplianceJobOut)
def get_compliance_job(job_id: str, db: Session = Depends(get_db)):
    job = compliance_engine.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_out(job, db)


def _job_to_out(job: ComplianceCheckJob, db: Session) -> schemas.ComplianceJobOut:
    result_out = None
    if job.result_id and job.result:
        scores_parsed = json.loads(job.result.scores_json)
        scores_map = scores_parsed.get("scores", {})

        # Build dimension score list from stored scores + dimension metadata
        dims = compliance_engine._get_active_dimensions(db)
        dim_lookup = {d.code: d for d in dims}
        dimension_scores = []
        for code, entry in scores_map.items():
            dim = dim_lookup.get(code)
            if dim and isinstance(entry, dict):
                dimension_scores.append(schemas.DimensionScoreOut(
                    code=code,
                    name=dim.name,
                    framework=dim.framework,
                    score=entry.get("score", 1),
                    rationale=entry.get("rationale", ""),
                ))

        result_out = schemas.ComplianceResultOut(
            id=job.result.id,
            version_id=job.result.version_id,
            gold_score=job.result.gold_score,
            blocked=job.result.blocked,
            scores=dimension_scores,
            anomaly=schemas.AnomalyOut(
                result=job.result.anomaly_result,
                confidence=job.result.anomaly_confidence,
                reason=job.result.anomaly_reason,
            ),
            cache_valid=job.result.cache_valid,
            created_at=job.result.created_at,
        )

    return schemas.ComplianceJobOut(
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
