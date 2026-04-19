"""DELETE /briefs/{id} — authorisation + hard-delete behaviour."""

import pytest

from app.auth import hash_password
from app.models import Brief, User


# ── helpers ──────────────────────────────────────────────────────────────────

def _login(client, email, password):
    resp = client.post("/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_user(db, email, role):
    user = User(email=email, name=f"Test {role}", role=role,
                password_hash=hash_password("pw"), is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_brief(db, owner_id, status="In Progress"):
    brief = Brief(
        brief_builder_id=owner_id,
        interviewer_id=owner_id,
        status=status,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


# ── test cases ───────────────────────────────────────────────────────────────

def test_maker_deletes_own_draft_succeeds(client, db, test_user, auth_headers):
    brief = _make_brief(db, test_user.user_id, status="In Progress")

    resp = client.delete(f"/briefs/{brief.brief_id}", headers=auth_headers)

    assert resp.status_code == 204, resp.text
    assert db.query(Brief).filter(Brief.brief_id == brief.brief_id).first() is None


def test_maker_cannot_delete_own_completed_brief(client, db, test_user, auth_headers):
    brief = _make_brief(db, test_user.user_id, status="Complete")

    resp = client.delete(f"/briefs/{brief.brief_id}", headers=auth_headers)

    assert resp.status_code == 403, resp.text
    assert "draft" in resp.json()["detail"].lower()
    assert db.query(Brief).filter(Brief.brief_id == brief.brief_id).first() is not None


def test_maker_cannot_delete_other_users_brief(client, db, test_user, auth_headers):
    other = _make_user(db, "other@test.local", "Maker")
    brief = _make_brief(db, other.user_id, status="In Progress")

    resp = client.delete(f"/briefs/{brief.brief_id}", headers=auth_headers)

    assert resp.status_code == 403, resp.text
    assert "own" in resp.json()["detail"].lower()
    assert db.query(Brief).filter(Brief.brief_id == brief.brief_id).first() is not None


def test_checker_can_delete_any_in_progress_brief(client, db, test_user, second_user):
    # second_user is a Checker per conftest.py
    maker_brief = _make_brief(db, test_user.user_id, status="In Progress")
    checker_headers = _login(client, "approver@test.local", "pw")

    resp = client.delete(f"/briefs/{maker_brief.brief_id}", headers=checker_headers)

    assert resp.status_code == 204, resp.text
    assert db.query(Brief).filter(Brief.brief_id == maker_brief.brief_id).first() is None


def test_admin_can_delete_completed_brief(client, db, test_user):
    admin = _make_user(db, "admin@test.local", "Admin")
    completed = _make_brief(db, test_user.user_id, status="Complete")
    admin_headers = _login(client, "admin@test.local", "pw")

    resp = client.delete(f"/briefs/{completed.brief_id}", headers=admin_headers)

    assert resp.status_code == 204, resp.text
    assert db.query(Brief).filter(Brief.brief_id == completed.brief_id).first() is None


def test_delete_nonexistent_brief_returns_404(client, auth_headers):
    resp = client.delete("/briefs/nonexistent-id-1234", headers=auth_headers)
    assert resp.status_code == 404, resp.text


@pytest.fixture
def second_user(db):
    """Override conftest's second_user with the right login password.

    conftest's second_user uses password 'approverpass' for auth_headers,
    but this test file's _login helper uses 'pw'. Unify by creating our
    own fixture with 'pw' so _login works uniformly.
    """
    user = User(
        email="approver@test.local",
        name="Test Checker",
        role="Checker",
        password_hash=hash_password("pw"),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
