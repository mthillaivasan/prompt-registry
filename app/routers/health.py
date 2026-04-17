from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db, get_db_info

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    info = get_db_info()
    return {
        "status": "ok",
        "database": info["type"],
        "database_fallback": info["fallback"],
        "database_target": info["url_hint"],
    }
