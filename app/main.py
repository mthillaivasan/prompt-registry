import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app.models import (  # noqa: F401 — imports register all models with Base
    AuditLog,
    ComplianceCheck,
    ComplianceCheckJob,
    InjectionPattern,
    Prompt,
    PromptVersion,
    ScoringDimension,
    UpgradeProposal,
    User,
)
from app.routers import auth as auth_router
from app.routers import health as health_router
from app.routers import prompts as prompts_router
from app.routers import versions as versions_router
from app.seed import run_seed
from app.triggers import create_triggers_and_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("JWT_SECRET_KEY"):
        raise RuntimeError("JWT_SECRET_KEY environment variable is required")

    Base.metadata.create_all(bind=engine)
    create_triggers_and_indexes(engine)
    run_seed()

    yield


app = FastAPI(
    title="Prompt Registry",
    description="Gold standard AI prompt governance for regulated financial services.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router.router)
app.include_router(health_router.router)
app.include_router(prompts_router.router)
app.include_router(versions_router.router)
