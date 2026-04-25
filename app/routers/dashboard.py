"""
Dashboard endpoint — Block 20.

Single read path: GET /dashboard returns the four-phase row payload per
prompt. Reads from records and config; layout decisions live in the
service helper. The endpoint is a thin filter parser.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from services import dashboard_view

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(
    owner: str = Query("me", description="`me` for own prompts, `all` for everyone."),
    risk_tier: str | None = Query(None),
    lifecycle: str | None = Query(
        None,
        description="at-brief | at-build | at-deployment | at-operation | retired-only",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    owner_id = current_user.user_id if owner == "me" else None
    rows = dashboard_view.build_dashboard(
        db,
        owner_id=owner_id,
        risk_tier=risk_tier,
        lifecycle_filter=lifecycle,
    )
    return {"prompts": rows}
