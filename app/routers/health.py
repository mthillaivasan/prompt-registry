import os

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, get_db_info

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    info = get_db_info()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return {
        "status": "ok",
        "database": info["type"],
        "database_target": info["url_hint"],
        "anthropic_key_set": bool(api_key),
        "anthropic_key_prefix": api_key[:12] + "..." if len(api_key) > 12 else "(not set)",
    }
