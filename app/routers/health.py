import os

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    try:
        key = os.getenv("ANTHROPIC_API_KEY", "")
        db_url = os.getenv("DATABASE_URL", "")
        db_type = "Postgres" if "postgres" in db_url else "SQLite"
        return {
            "status": "ok",
            "database": db_type,
            "anthropic_key_set": bool(key),
        }
    except Exception as e:
        return {
            "status": "degraded",
            "error": str(e),
        }
