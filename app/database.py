import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite:///./data/prompt_registry.db"
)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_is_sqlite = "sqlite" in DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

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
