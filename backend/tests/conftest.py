"""Test harness: a real Postgres, migrated with Alembic once per session, emptied before each test.

CI sets DATABASE_URL to a `services: postgres` container. Locally, if DATABASE_URL is not set, a bundled
Postgres is started with the `pgserver` package (no Docker or system install needed).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
os.environ["ENV"] = "test"
os.environ["AI_PROVIDER"] = "demo"
os.environ["RUN_WORKER"] = "false"

_pg = None
if not os.environ.get("TEST_DATABASE_URL"):
    import pgserver

    _pg = pgserver.get_server(str(BACKEND / ".pgdata"), cleanup_mode="stop")
    if "1 row" not in _pg.psql("SELECT 1 FROM pg_database WHERE datname='bolo_test'"):
        _pg.psql("CREATE DATABASE bolo_test")
    os.environ["TEST_DATABASE_URL"] = _pg.get_uri("bolo_test")
# The harness drops and recreates the schema, so never let it near a hosted database.
if "neon.tech" in os.environ["TEST_DATABASE_URL"] or "render.com" in os.environ["TEST_DATABASE_URL"]:
    raise RuntimeError("Refusing to run tests against a hosted database")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

TABLES = ["turns", "appointments", "calls", "patients", "doctors", "users", "clinics"]


@pytest.fixture(scope="session")
def migrated() -> None:
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True, capture_output=True)


@pytest.fixture
def db(migrated):
    from sqlalchemy import text

    from app.db import get_engine, session_factory

    with get_engine().begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    from app.ratelimit import limiter

    limiter.reset()
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def staff(client) -> dict:
    """A registered clinic with one staff user."""
    r = client.post(
        "/api/auth/register",
        json={"clinic_name": "Test Clinic", "name": "Asha", "email": "asha@example.com", "password": "correct-horse"},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def auth_headers(staff) -> dict[str, str]:
    return {"Authorization": f"Bearer {staff['token']}"}
