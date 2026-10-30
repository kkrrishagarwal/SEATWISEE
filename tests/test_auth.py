"""Unified auth: DB-backed admin, hashed passwords, resets, role resolution."""
import pytest

from database import db_manager as db
from services import auth_service


@pytest.fixture
def conn():
    c = db.get_conn(":memory:")
    db.seed_demo(c, n_applicants=5)
    return c


def test_admin_is_db_backed_and_hashed(conn):
    row = db.get_admin(conn, "admin")
    assert row["password_hash"].startswith("pbkdf2_sha256$") and "admin123" not in row["password_hash"]
    assert auth_service.authenticate(conn, "admin", "admin123")["role"] == "admin"
    assert auth_service.authenticate(conn, "ADMIN ", " admin123 ")["role"] == "admin"
    assert auth_service.authenticate(conn, "admin", "wrong") is None
    db.set_admin_password(conn, "admin", "stronger-pass")
    assert auth_service.authenticate(conn, "admin", "admin123") is None
    assert auth_service.authenticate(conn, "admin", "stronger-pass")["role"] == "admin"
    assert not db.admin_uses_default_password(conn)


def test_student_cannot_become_admin(conn):
    aid = db.register_account(conn, name="S", email="s@s.io", phone="1", address="x", password="secret1")
    res = auth_service.authenticate(conn, "s@s.io", "secret1")
    assert res["role"] == "student" and res["id"] == aid
    assert auth_service.authenticate(conn, "s@s.io", "nope") is None
    assert db.get_admin(conn, "s@s.io") is None


def test_password_reset_flow(conn):
    db.register_account(conn, name="R", email="r@r.io", phone="1", address="x", password="oldpass1")
    tok = db.create_password_reset(conn, "r@r.io")
    assert tok and len(tok) == 8
    assert not db.redeem_password_reset(conn, "r@r.io", "WRONG", "newpass1")
    assert db.redeem_password_reset(conn, "r@r.io", tok, "newpass1")
    assert not db.redeem_password_reset(conn, "r@r.io", tok, "again123")        # single use
    assert auth_service.authenticate(conn, "r@r.io", "newpass1")["role"] == "student"
    assert db.create_password_reset(conn, "ghost@x.y") is None


def test_duplicate_and_invalid_registration(conn):
    db.register_account(conn, name="A", email="dup@x.io", phone="1", address="x", password="secret1")
    with pytest.raises(ValueError):
        db.register_account(conn, name="B", email="DUP@x.io", phone="1", address="x", password="secret1")
    with pytest.raises(ValueError):
        db.register_account(conn, name="B", email="not-an-email", phone="1", address="x", password="secret1")
