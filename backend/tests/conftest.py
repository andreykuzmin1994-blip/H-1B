"""Shared pytest fixtures using an in-memory SQLite database.

SQLite doesn't support the recursive CTE syntax we use for subgraph traversal
in production, so graph-traversal tests are exercised at the builder level and
the subgraph SQL is tested against PostgreSQL integration tests only.
"""
from __future__ import annotations

import os
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Point the application at a throw-away SQLite file before we import models.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from h1b_engine.db import base  # noqa: E402
from h1b_engine.db import models  # noqa: E402,F401


@pytest.fixture(scope="function")
def engine():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)

    @event.listens_for(eng, "connect")
    def _fk_pragma(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    base.Base.metadata.create_all(eng)
    yield eng
    base.Base.metadata.drop_all(eng)


@pytest.fixture(scope="function")
def session_factory(engine):
    # Rebind the module-global SessionLocal so ``get_session`` uses our engine.
    base._engine = engine
    base.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield base.SessionLocal
    base._engine = None
    base.SessionLocal = None
