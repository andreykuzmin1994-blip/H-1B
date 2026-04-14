"""Tests for the ingestion_run context manager."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from h1b_engine.db.models import IngestionRun
from h1b_engine.ingest.common import ingestion_run


def test_ingestion_run_records_success(session_factory):
    with ingestion_run("unit-test-success", {"foo": "bar"}) as (session, run):
        assert run.id is not None
        assert run.status == "running"
    s = session_factory()
    rows = s.execute(select(IngestionRun).where(IngestionRun.source == "unit-test-success")).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "success"
    assert rows[0].finished_at is not None
    assert rows[0].error is None


def test_ingestion_run_records_failure_once(session_factory):
    """When the wrapped block raises, exactly one IngestionRun row should exist
    and it should be marked failed with the exception text."""

    with pytest.raises(ValueError, match="boom"):
        with ingestion_run("unit-test-failure") as (session, run):
            raise ValueError("boom")

    s = session_factory()
    rows = (
        s.execute(
            select(IngestionRun).where(IngestionRun.source == "unit-test-failure")
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].error is not None
    assert "boom" in rows[0].error
    assert rows[0].finished_at is not None
