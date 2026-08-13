"""Pytest fixtures: spin up the app against an isolated temp database."""
from __future__ import annotations

import os
import tempfile
import uuid

import pytest

# Configure the environment BEFORE importing the app (settings are cached).
_db_fd, _db_path = tempfile.mkstemp(suffix=".db", prefix="shoptest_")
os.close(_db_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough-1234567890"
os.environ["ENVIRONMENT"] = "development"
os.environ["ADMIN_USERNAME"] = ""
os.environ["ADMIN_PASSWORD"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(bind=engine)
    yield
    try:
        os.remove(_db_path)
    except OSError:
        pass


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def shopkeeper():
    """Create a fresh shopkeeper with a unique name and return credentials."""
    username = f"keeper_{uuid.uuid4().hex[:8]}"
    password = "SuperSecret123"
    with SessionLocal() as db:
        db.add(User(username=username, hashed_password=hash_password(password)))
        db.commit()
    return {"username": username, "password": password}


@pytest.fixture()
def auth_headers(client, shopkeeper):
    res = client.post("/api/auth/login", json=shopkeeper)
    assert res.status_code == 200, res.text
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
