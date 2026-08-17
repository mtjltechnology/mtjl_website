"""
Fixtures shared by integration tests.
DATABASE_URL must be set to SQLite BEFORE db is imported (which happens
when main.py is imported). Setting it at module level here ensures it's in
place before any fixture function runs.

StaticPool is required so all sessions created by the app routes and by test
fixtures share the same in-memory database (SQLite :memory: is connection-scoped
by default — each new connection gets an empty database).
"""
import os
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from db import get_session
from limiter import limiter
from models import PilotQASubscriber  # noqa: F401 — registra a tabela no SQLModel.metadata antes do create_all

_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SQLModel.metadata.create_all(_TEST_ENGINE)


def _override_get_session():
    with Session(_TEST_ENGINE) as session:
        yield session


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate every table after each test so tests don't share state."""
    yield
    with Session(_TEST_ENGINE) as s:
        for table in reversed(SQLModel.metadata.sorted_tables):
            s.execute(table.delete())
        s.commit()


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Each test starts with a clean rate-limit counter so tests don't leak
    request counts into each other (slowapi keys by remote address + URL,
    and TestClient always uses the same fake remote address "testclient")."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(name="db_session")
def db_session_fixture():
    with Session(_TEST_ENGINE) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture():
    from main import app
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
