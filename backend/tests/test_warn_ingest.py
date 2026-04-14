"""Tests for the WARN / Layoffs.fyi ingester."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from h1b_engine.db.models import Employer, LayoffEvent
from h1b_engine.ingest.warn import ingest_rows, normalize_row


def test_normalize_row_variant_columns_and_state_default():
    """Column-alias coverage across the main WARN dialects."""
    record = normalize_row(
        {
            "Company Name": "Oracle America Inc",
            "Date of Notice": "2026-02-01",
            "Layoff Date": "2026-03-15",
            "Number Affected": "250",
            "City": "Redwood City",
            # Note: no state column — default_state must fill it.
            "Layoff Type": "Permanent reduction in force",
            "Warn Number": "WARN-2026-0123",
        },
        source="WARN_STATE_CA",
        default_state="CA",
        source_url="https://edd.ca.gov/warn",
    )
    assert record is not None
    assert record.employer_name == "Oracle America Inc"
    assert record.notice_date == date(2026, 2, 1)
    assert record.effective_date == date(2026, 3, 15)
    assert record.workers_affected == 250
    assert record.location_city == "Redwood City"
    assert record.location_state == "CA"
    assert record.reason == "Permanent reduction in force"
    assert record.external_id == "WARN-2026-0123"
    assert record.source == "WARN_STATE_CA"
    assert record.source_url == "https://edd.ca.gov/warn"


def test_normalize_row_returns_none_without_employer():
    assert normalize_row({"City": "Austin"}, source="WARN_FEDERAL") is None


def test_ingest_rows_links_matching_employer_and_dedupes(session_factory):
    session = session_factory()
    emp = Employer(
        name="Acme Tech Inc",
        name_normalized="ACME TECH",
        state="WA",
        naics_code="541512",
        total_lca_count=0,
    )
    session.add(emp)
    session.commit()
    emp_id = emp.id

    rows = [
        {
            "Company": "Acme Tech Inc",
            "Notice Date": "2026-01-10",
            "Effective Date": "2026-03-10",
            "Workers Affected": 120,
            "State": "WA",
            "City": "Seattle",
            "Reason": "Engineering reorganization",
            "Case Number": "WA-WARN-42",
        },
        # Duplicate of the first row — must be skipped by (source, external_id).
        {
            "Company": "Acme Tech Inc",
            "Notice Date": "2026-01-10",
            "Effective Date": "2026-03-10",
            "Workers Affected": 120,
            "State": "WA",
            "Case Number": "WA-WARN-42",
        },
        # Employer not in DB — still recorded with a null employer_id.
        {
            "Company": "Unknown Startup Co",
            "Effective Date": "2026-02-01",
            "Workers Affected": 30,
            "State": "TX",
            "Case Number": "TX-WARN-1",
        },
    ]

    inserted = ingest_rows(rows, source="WARN_STATE_WA", default_state="WA")
    assert inserted == 2

    events = (
        session_factory()
        .execute(select(LayoffEvent).order_by(LayoffEvent.id))
        .scalars()
        .all()
    )
    assert len(events) == 2

    linked = [e for e in events if e.employer_id is not None][0]
    assert linked.employer_id == emp_id
    assert linked.workers_affected == 120
    assert linked.reason == "Engineering reorganization"

    unlinked = [e for e in events if e.employer_id is None][0]
    assert unlinked.employer_name_raw == "Unknown Startup Co"
    assert unlinked.location_state == "TX"


def test_ingest_rows_second_call_respects_unique_constraint(session_factory):
    emp = Employer(
        name="Beta Corp",
        name_normalized="BETA",
        state="CO",
        naics_code="541512",
    )
    session = session_factory()
    session.add(emp)
    session.commit()

    row = {
        "Company": "Beta Corp",
        "State": "CO",
        "Effective Date": "2026-05-01",
        "Case Number": "CO-1",
    }
    first = ingest_rows([row], source="WARN_STATE_CO", default_state="CO")
    second = ingest_rows([row], source="WARN_STATE_CO", default_state="CO")
    assert first == 1
    assert second == 0

    count = (
        session_factory()
        .execute(select(LayoffEvent).where(LayoffEvent.external_id == "CO-1"))
        .scalars()
        .all()
    )
    assert len(count) == 1
