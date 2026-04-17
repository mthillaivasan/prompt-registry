import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

_SQLITE_FALLBACK = "sqlite:///./data/prompt_registry.db"

DATABASE_URL = os.environ.get("DATABASE_URL", _SQLITE_FALLBACK)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = "sqlite" in DATABASE_URL
_using_fallback = False

# Ensure SQLite parent directory exists
if _is_sqlite:
    db_path = DATABASE_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    pass


def _create_engine_safe(url, is_sqlite):
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    eng = create_engine(url, connect_args=connect_args)
    if not is_sqlite:
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Connected to Postgres: %s", url.split("@")[-1] if "@" in url else "(url)")
        except Exception as e:
            logger.warning("Postgres connection failed: %s — falling back to SQLite", e)
            return None
    return eng


if _is_sqlite:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = _create_engine_safe(DATABASE_URL, False)
    if engine is None:
        logger.warning("Using SQLite fallback at %s", _SQLITE_FALLBACK)
        DATABASE_URL = _SQLITE_FALLBACK
        _is_sqlite = True
        _using_fallback = True
        engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


if _is_sqlite:
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_info() -> dict:
    return {
        "type": "SQLite" if _is_sqlite else "Postgres",
        "fallback": _using_fallback,
        "url_hint": DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL.split("///")[-1],
    }
