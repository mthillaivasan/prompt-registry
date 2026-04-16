"""
Test fixtures.

Each test gets a fresh in-memory SQLite database with all tables created and
the injection-pattern seed loaded. The scanner cache is cleared between tests
so cache state never leaks between cases.
"""

import os

# JWT_SECRET_KEY must be set before app modules are imported (lifespan checks it).
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.seed import _seed_patterns
from services import injection_scanner


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    _seed_patterns(session)
    injection_scanner.clear_cache()
    try:
        yield session
    finally:
        injection_scanner.clear_cache()
        session.close()
        engine.dispose()
