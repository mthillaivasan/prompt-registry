"""
Test fixtures.

Sets JWT_SECRET_KEY and points DATABASE_URL at a temp SQLite file before
any app modules are imported. Each test gets a freshly-initialised database
(tables dropped, recreated, triggers reapplied, seed reloaded), and the
scanner cache is cleared so cache state never leaks between tests.
"""

import os
import tempfile

# Must run before any app imports — these env vars are read at module-import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

_temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_temp_db.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_temp_db.name}"

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.seed import run_seed
from app.seed_phase2 import run_phase2_seed
from app.triggers import create_triggers_and_indexes
from services import injection_scanner


@pytest.fixture(autouse=True)
def fresh_database():
    """Reset the database before each test, then run seed and triggers."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    create_triggers_and_indexes(engine)
    run_seed()
    run_phase2_seed()
    injection_scanner.clear_cache()
    yield
    injection_scanner.clear_cache()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    # No `with` block — we don't want lifespan running again per request.
    return TestClient(app)


@pytest.fixture
def test_user(db):
    """A standard Maker user available in every HTTP test."""
    user = User(
        email="author@test.local",
        name="Test Maker",
        role="Maker",
        password_hash=hash_password("authorpass"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def second_user(db):
    user = User(
        email="approver@test.local",
        name="Test Checker",
        role="Checker",
        password_hash=hash_password("approverpass"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(client, test_user):
    resp = client.post(
        "/auth/login",
        data={"username": "author@test.local", "password": "authorpass"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
