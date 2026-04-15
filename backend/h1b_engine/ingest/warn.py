"""WARN Act mass-layoff notice ingestion.

Primary sources
---------------
The federal Worker Adjustment and Retraining Notification (WARN) Act requires
employers with 100+ workers to give 60 days' written notice before any mass
layoff that affects 50+ employees. Notices are filed with each state's labor
department; most states publish them as CSV or HTML tables.

This ingester consumes:

* State WARN CSVs saved under ``data/raw/warn/<state>/``. Column names vary
  widely so we use a flexible alias map (see ``COLUMN_ALIASES``).
* Federal aggregate WARN feeds from WARNTracker and similar services.
* Layoffs.fyi CSV export as a non-WARN supplement (tech remote-worker layoffs
  often fall below the WARN 50-worker threshold because they span states).

The linkage to H-1B filings happens at scoring time (see
``score/detectors.py::detect_layoffs_with_concurrent_h1b``): this module just
normalizes raw notices and attaches them to the best-matching employer.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import select

from h1b_engine.db.models import Employer, LayoffEvent
from h1b_engine.ingest.common import ingestion_run, read_table
from h1b_engine.utils import normalize_employer_name

log = logging.getLogger(__name__)


# Column aliases used to normalize heterogeneous state WARN CSVs.
# Keys are lowercased, punctuation stripped.
COLUMN_ALIASES: dict[str, str] = {
    # Employer
    "employer": "employer_name",
    "employer_name": "employer_name",
    "company": "employer_name",
    "company_name": "employer_name",
    "business": "employer_name",
    # Notice date
    "notice_date": "notice_date",
    "warn_date": "notice_date",
    "received_date": "notice_date",
    "date_of_notice": "notice_date",
    "received": "notice_date",
    # Effective date
    "effective_date": "effective_date",
    "layoff_date": "effective_date",
    "separation_date": "effective_date",
    "date_of_separation": "effective_date",
    "lo_date": "effective_date",
    "closing_date": "effective_date",
    # Workers
    "workers_affected": "workers_affected",
    "affected_workers": "workers_affected",
    "employees_affected": "workers_affected",
    "number_affected": "workers_affected",
    "num_workers": "workers_affected",
    "total_affected": "workers_affected",
    "laidoff": "workers_affected",
    "laid_off": "workers_affected",
    # Location
    "city": "location_city",
    "location_city": "location_city",
    "state": "location_state",
    "location_state": "location_state",
    "st": "location_state",
    "zip": "location_zip",
    "zipcode": "location_zip",
    "postal_code": "location_zip",
    # Reason / industry
    "reason": "reason",
    "closing_type": "reason",
    "closure_type": "reason",
    "layoff_type": "reason",
    "industry": "industry",
    "naics": "industry",
    # External id
    "case_number": "external_id",
    "warn_number": "external_id",
    "notice_id": "external_id",
    "id": "external_id",
}


@dataclass
class LayoffRecord:
    employer_name: str
    source: str
    notice_date: date | None = None
    effective_date: date | None = None
    workers_affected: int | None = None
    location_city: str | None = None
    location_state: str | None = None
    location_zip: str | None = None
    reason: str | None = None
    industry: str | None = None
    source_url: str | None = None
    external_id: str | None = None
    raw: dict[str, Any] | None = None


def _norm_key(key: str) -> str:
    return (
        str(key)
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("/", "_")
        .replace(".", "")
    )


def _str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    return s or None


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        parsed = pd.to_datetime(value, errors="coerce")
    except Exception:
        return None
    if parsed is None or pd.isna(parsed):
        return None
    return parsed.date()


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def normalize_row(
    raw: dict[str, Any],
    *,
    source: str,
    default_state: str | None = None,
    source_url: str | None = None,
) -> LayoffRecord | None:
    """Map a raw WARN / layoffs.fyi row to our canonical schema.

    Returns ``None`` when the row lacks an employer name (nothing to link on).
    """
    canonical: dict[str, Any] = {}
    for key, value in raw.items():
        if key is None:
            continue
        alias = COLUMN_ALIASES.get(_norm_key(str(key)))
        if alias:
            # Prefer the first non-empty value if multiple source columns collapse.
            if canonical.get(alias) in (None, ""):
                canonical[alias] = value

    employer_name = _str(canonical.get("employer_name"))
    if not employer_name:
        return None

    state = _str(canonical.get("location_state")) or default_state
    if state:
        state = state.upper()[:2]

    return LayoffRecord(
        employer_name=employer_name,
        source=source,
        notice_date=_coerce_date(canonical.get("notice_date")),
        effective_date=_coerce_date(canonical.get("effective_date")),
        workers_affected=_coerce_int(canonical.get("workers_affected")),
        location_city=_str(canonical.get("location_city")),
        location_state=state,
        location_zip=_str(canonical.get("location_zip")),
        reason=_str(canonical.get("reason")),
        industry=_str(canonical.get("industry")),
        source_url=source_url,
        external_id=_str(canonical.get("external_id")),
        raw=raw,
    )


def _match_employer(session, name: str, state: str | None) -> Employer | None:
    """Best-effort match of a WARN employer name against the employers table.

    Matches on ``(normalized name, state)`` when possible; falls back to name
    alone (taking the first hit). Returning ``None`` still stores the layoff
    event with the raw employer name for later joins after LCA ingest.
    """
    name_norm = normalize_employer_name(name)
    if not name_norm:
        return None
    if state:
        emp = session.execute(
            select(Employer).where(
                Employer.name_normalized == name_norm,
                Employer.state == state,
            )
        ).scalar_one_or_none()
        if emp is not None:
            return emp
    return session.execute(
        select(Employer).where(Employer.name_normalized == name_norm).limit(1)
    ).scalar_one_or_none()


def _upsert_layoff_event(session, record: LayoffRecord) -> int:
    """Insert a layoff event unless ``(source, external_id)`` already exists.

    Returns 1 if inserted, 0 if skipped.
    """
    if record.external_id:
        existing = session.execute(
            select(LayoffEvent.id).where(
                LayoffEvent.source == record.source,
                LayoffEvent.external_id == record.external_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return 0

    employer = _match_employer(session, record.employer_name, record.location_state)
    session.add(
        LayoffEvent(
            employer_id=employer.id if employer else None,
            employer_name_raw=record.employer_name,
            source=record.source,
            notice_date=record.notice_date,
            effective_date=record.effective_date,
            workers_affected=record.workers_affected,
            location_city=record.location_city,
            location_state=record.location_state,
            location_zip=record.location_zip,
            reason=record.reason,
            industry=record.industry,
            source_url=record.source_url,
            external_id=record.external_id,
            raw=record.raw,
        )
    )
    return 1


def ingest_rows(
    rows: Iterable[dict[str, Any]],
    *,
    source: str,
    default_state: str | None = None,
    source_url: str | None = None,
) -> int:
    """Ingest an iterable of raw WARN / layoffs.fyi records."""
    rows_in = 0
    rows_out = 0
    params = {
        "source": source,
        "default_state": default_state,
        "source_url": source_url,
    }
    with ingestion_run("warn", params) as (session, run):
        for raw in rows:
            rows_in += 1
            record = normalize_row(
                raw,
                source=source,
                default_state=default_state,
                source_url=source_url,
            )
            if record is None:
                continue
            rows_out += _upsert_layoff_event(session, record)
        run.rows_in = rows_in
        run.rows_out = rows_out
    log.info(
        "WARN ingest complete: source=%s rows_in=%d rows_out=%d",
        source,
        rows_in,
        rows_out,
    )
    return rows_out


def ingest_file(
    path: Path,
    *,
    source: str | None = None,
    default_state: str | None = None,
    source_url: str | None = None,
) -> int:
    """Ingest a single WARN / layoffs.fyi CSV or Excel file.

    ``source`` defaults to ``WARN_STATE_{XX}`` when ``default_state`` is given,
    otherwise falls back to ``WARN_FEDERAL``. Use ``LAYOFFS_FYI`` explicitly for
    Layoffs.fyi export.
    """
    frame = read_table(path)

    resolved_source = source or (
        f"WARN_STATE_{default_state.upper()}" if default_state else "WARN_FEDERAL"
    )
    frame.columns = [str(c) for c in frame.columns]
    return ingest_rows(
        frame.to_dict(orient="records"),
        source=resolved_source,
        default_state=default_state,
        source_url=source_url,
    )
