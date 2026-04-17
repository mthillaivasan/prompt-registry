import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.dependencies import get_current_user
from app.models import (  # noqa: F401 — imports register all models with Base
    AuditLog,
    Brief,
    ComplianceCheck,
    ComplianceCheckJob,
    InjectionPattern,
    Prompt,
    PromptComponent,
    PromptTemplate,
    PromptVersion,
    ScoringDimension,
    UpgradeProposal,
    User,
)
from app.routers import auth as auth_router
from app.routers import briefs as briefs_router
from app.routers import compliance as compliance_router
from app.routers import health as health_router
from app.routers import prompts as prompts_router
from app.routers import templates as templates_router
from app.routers import upgrade as upgrade_router
from app.routers import versions as versions_router
from app.seed import run_seed
from app.triggers import create_triggers_and_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("JWT_SECRET_KEY"):
        print("WARNING: JWT_SECRET_KEY not set — using fallback (not safe for production)")
        os.environ["JWT_SECRET_KEY"] = "INSECURE-FALLBACK-CHANGE-ME"

    try:
        Base.metadata.create_all(bind=engine)
        create_triggers_and_indexes(engine)
        run_seed()
        print("Startup initialization complete")
    except Exception as e:
        print(f"WARNING: Startup initialization failed: {e}")
        print("App will start but may have limited functionality")

    yield


app = FastAPI(
    title="Prompt Registry",
    description="Gold standard AI prompt governance for regulated financial services.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return FileResponse("static/base.html")


@app.get("/audit-log")
def list_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    if action:
        query = query.filter(AuditLog.action == action)
    entries = query.offset(skip).limit(limit).all()
    return [
        {
            "log_id": e.log_id,
            "timestamp": e.timestamp,
            "user_id": e.user_id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "detail": e.detail,
        }
        for e in entries
    ]


app.include_router(auth_router.router)
app.include_router(health_router.router)
app.include_router(briefs_router.router)
app.include_router(compliance_router.router)
app.include_router(prompts_router.router)
app.include_router(templates_router.router)
app.include_router(upgrade_router.router)
app.include_router(versions_router.router)
app.mount("/static", StaticFiles(directory="static"), name="static")
