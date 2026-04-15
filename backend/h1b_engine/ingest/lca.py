"""DOL OFLC LCA Disclosure Data ingestion.

Source: https://www.dol.gov/agencies/eta/foreign-labor/performance

The DOL publishes quarterly Excel/CSV files. Column names drift slightly between
fiscal years. This module maintains a column-name -> canonical-field map so we
can normalize regardless of the source year.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Iterator

import pandas as pd
from sqlalchemy import select

from h1b_engine.db.models import Employer, LcaFiling
from h1b_engine.ingest.common import chunked, ingestion_run, read_table
from h1b_engine.utils import annualize_wage, normalize_employer_name

log = logging.getLogger(__name__)

# Map of raw column name variants -> canonical field.
COLUMN_MAP: dict[str, str] = {
    # core identifiers
    "CASE_NUMBER": "case_number",
    "CASE_STATUS": "case_status",
    "VISA_CLASS": "visa_class",
    # employer
    "EMPLOYER_NAME": "employer_name",
    "EMPLOYER_BUSINESS_NAME": "employer_name",
    "EMPLOYER_ADDRESS1": "employer_address1",
    "EMPLOYER_ADDRESS": "employer_address1",
    "EMPLOYER_CITY": "employer_city",
    "EMPLOYER_STATE": "employer_state",
    "EMPLOYER_POSTAL_CODE": "employer_zip",
    "EMPLOYER_ZIP": "employer_zip",
    # classification
    "NAICS_CODE": "naics_code",
    "SOC_CODE": "soc_code",
    "SOC_TITLE": "soc_title",
    "SOC_NAME": "soc_title",
    "JOB_TITLE": "job_title",
    # wages
    "WAGE_RATE_OF_PAY_FROM": "wage_from",
    "WAGE_RATE_FROM": "wage_from",
    "WAGE_UNIT_OF_PAY": "wage_unit",
    "WAGE_RATE_PAY_UNIT": "wage_unit",
    "PREVAILING_WAGE": "prevailing_wage",
    "PW_UNIT_OF_PAY": "pw_unit",
    "PW_WAGE_LEVEL": "pw_level",
    # worksite
    "WORKSITE_CITY": "worksite_city",
    "WORKSITE_STATE": "worksite_state",
    "WORKSITE_POSTAL_CODE": "worksite_zip",
    # placement
    "SECONDARY_ENTITY_BUSINESS_NAME": "secondary_entity",
    "SECONDARY_ENTITY": "secondary_entity",
    "TOTAL_WORKER_POSITIONS": "total_workers",
    "TOTAL_WORKERS": "total_workers",
    # dates
    "RECEIVED_DATE": "received_date",
    "CASE_SUBMITTED": "received_date",
    "DECISION_DATE": "decision_date",
}


@dataclass
class LcaRow:
    case_number: str
    case_status: str | None = None
    visa_class: str | None = None
    employer_name: str | None = None
    employer_address1: str | None = None
    employer_city: str | None = None
    employer_state: str | None = None
    employer_zip: str | None = None
    naics_code: str | None = None
    soc_code: str | None = None
    soc_title: str | None = None
    job_title: str | None = None
    wage_from: float | None = None
    wage_unit: str | None = None
    prevailing_wage: float | None = None
    pw_unit: str | None = None
    worksite_city: str | None = None
    worksite_state: str | None = None
    worksite_zip: str | None = None
    secondary_entity: str | None = None
    total_workers: int | None = None
    received_date: date | None = None
    decision_date: date | None = None
    fiscal_year: int | None = None
    raw: dict = field(default_factory=dict)


def _coerce_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value, errors="coerce").date()
    except Exception:
        return None


def _coerce_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip()
    return s or None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("$", "").strip()
        if not value:
            return None
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> int | None:
    f = _coerce_float(value)
    return int(f) if f is not None else None


def normalize_row(raw: dict, fiscal_year: int | None = None) -> LcaRow | None:
    """Map a raw LCA row dict to our canonical schema. Returns None if unparseable."""
    canonical: dict = {}
    for key, value in raw.items():
        if not key:
            continue
        canon = COLUMN_MAP.get(str(key).strip().upper())
        if canon:
            canonical[canon] = value

    case_number = _coerce_str(canonical.get("case_number"))
    if not case_number:
        return None

    row = LcaRow(case_number=case_number, raw=raw)
    row.case_status = _coerce_str(canonical.get("case_status"))
    row.visa_class = _coerce_str(canonical.get("visa_class"))
    row.employer_name = _coerce_str(canonical.get("employer_name"))
    row.employer_address1 = _coerce_str(canonical.get("employer_address1"))
    row.employer_city = _coerce_str(canonical.get("employer_city"))
    row.employer_state = _coerce_str(canonical.get("employer_state"))
    row.employer_zip = _coerce_str(canonical.get("employer_zip"))
    row.naics_code = _coerce_str(canonical.get("naics_code"))
    if row.naics_code:
        row.naics_code = row.naics_code[:6]
    row.soc_code = _coerce_str(canonical.get("soc_code"))
    row.soc_title = _coerce_str(canonical.get("soc_title"))
    row.job_title = _coerce_str(canonical.get("job_title"))
    row.wage_from = _coerce_float(canonical.get("wage_from"))
    row.wage_unit = _coerce_str(canonical.get("wage_unit"))
    row.prevailing_wage = _coerce_float(canonical.get("prevailing_wage"))
    row.pw_unit = _coerce_str(canonical.get("pw_unit"))
    row.worksite_city = _coerce_str(canonical.get("worksite_city"))
    row.worksite_state = _coerce_str(canonical.get("worksite_state"))
    row.worksite_zip = _coerce_str(canonical.get("worksite_zip"))
    row.secondary_entity = _coerce_str(canonical.get("secondary_entity"))
    row.total_workers = _coerce_int(canonical.get("total_workers"))
    row.received_date = _coerce_date(canonical.get("received_date"))
    row.decision_date = _coerce_date(canonical.get("decision_date"))
    row.fiscal_year = fiscal_year
    return row


def read_file(path: Path) -> Iterator[dict]:
    """Iterate over rows of an LCA disclosure file (Parquet, CSV, or Excel).

    Parquet is strongly preferred for the DOL quarterly dumps: a 3 GB CSV
    typically compresses to ~300 MB of Parquet with no data loss. See
    ``scripts/download_data.py`` for the CSV -> Parquet conversion helper.
    """
    frame = read_table(path)
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    for record in frame.to_dict(orient="records"):
        yield record


def upsert_employer(session, row: LcaRow) -> Employer | None:
    if not row.employer_name or not row.employer_state:
        return None
    name_norm = normalize_employer_name(row.employer_name)
    stmt = select(Employer).where(
        Employer.name_normalized == name_norm,
        Employer.state == row.employer_state,
    )
    emp = session.execute(stmt).scalar_one_or_none()
    if emp is None:
        emp = Employer(
            name=row.employer_name,
            name_normalized=name_norm,
            address_line1=row.employer_address1,
            city=row.employer_city,
            state=row.employer_state,
            zip=row.employer_zip,
            naics_code=row.naics_code,
            first_filing_date=row.received_date,
            last_filing_date=row.received_date,
            total_lca_count=0,
        )
        session.add(emp)
        session.flush()
    else:
        if row.received_date:
            if not emp.first_filing_date or row.received_date < emp.first_filing_date:
                emp.first_filing_date = row.received_date
            if not emp.last_filing_date or row.received_date > emp.last_filing_date:
                emp.last_filing_date = row.received_date
        if not emp.naics_code and row.naics_code:
            emp.naics_code = row.naics_code
        if not emp.address_line1 and row.employer_address1:
            emp.address_line1 = row.employer_address1
            emp.city = row.employer_city
            emp.zip = row.employer_zip
    return emp


def ingest_file(path: Path, fiscal_year: int | None = None, batch_size: int = 1000) -> int:
    """Ingest a single LCA disclosure file. Returns rows inserted."""
    rows_in = 0
    rows_out = 0
    with ingestion_run("lca", {"file": str(path), "fiscal_year": fiscal_year}) as (session, run):
        for batch in chunked(read_file(path), batch_size):
            for raw in batch:
                rows_in += 1
                row = normalize_row(raw, fiscal_year=fiscal_year)
                if row is None:
                    continue
                # Skip duplicates by case_number
                existing = session.execute(
                    select(LcaFiling.id).where(LcaFiling.case_number == row.case_number)
                ).scalar_one_or_none()
                if existing is not None:
                    continue

                emp = upsert_employer(session, row)
                wage_annual = annualize_wage(row.wage_from, row.wage_unit)
                pw_annual = annualize_wage(row.prevailing_wage, row.pw_unit)
                ratio = (wage_annual / pw_annual) if (wage_annual and pw_annual) else None

                filing = LcaFiling(
                    case_number=row.case_number,
                    case_status=row.case_status,
                    employer_id=emp.id if emp else None,
                    employer_name_raw=row.employer_name,
                    naics_code=row.naics_code,
                    soc_code=row.soc_code,
                    soc_title=row.soc_title,
                    job_title=row.job_title,
                    wage_from=row.wage_from,
                    wage_unit=row.wage_unit,
                    wage_annualized=wage_annual,
                    prevailing_wage=row.prevailing_wage,
                    pw_unit=row.pw_unit,
                    pw_annualized=pw_annual,
                    wage_ratio=ratio,
                    worksite_city=row.worksite_city,
                    worksite_state=row.worksite_state,
                    worksite_zip=row.worksite_zip,
                    secondary_entity=row.secondary_entity,
                    total_workers=row.total_workers,
                    visa_class=row.visa_class,
                    received_date=row.received_date,
                    decision_date=row.decision_date,
                    fiscal_year=fiscal_year,
                )
                session.add(filing)
                if emp is not None:
                    emp.total_lca_count += 1
                rows_out += 1
            session.flush()
        run.rows_in = rows_in
        run.rows_out = rows_out
    log.info("LCA ingest complete: %d rows read, %d filings inserted", rows_in, rows_out)
    return rows_out


def ingest_rows(rows: Iterable[dict], fiscal_year: int | None = None) -> int:
    """In-memory ingest (useful for tests and Kaggle prototypes)."""
    rows_out = 0
    with ingestion_run("lca", {"in_memory": True, "fiscal_year": fiscal_year}) as (session, run):
        for raw in rows:
            row = normalize_row(raw, fiscal_year=fiscal_year)
            if row is None:
                continue
            existing = session.execute(
                select(LcaFiling.id).where(LcaFiling.case_number == row.case_number)
            ).scalar_one_or_none()
            if existing is not None:
                continue
            emp = upsert_employer(session, row)
            wage_annual = annualize_wage(row.wage_from, row.wage_unit)
            pw_annual = annualize_wage(row.prevailing_wage, row.pw_unit)
            ratio = (wage_annual / pw_annual) if (wage_annual and pw_annual) else None
            session.add(
                LcaFiling(
                    case_number=row.case_number,
                    case_status=row.case_status,
                    employer_id=emp.id if emp else None,
                    employer_name_raw=row.employer_name,
                    naics_code=row.naics_code,
                    soc_code=row.soc_code,
                    soc_title=row.soc_title,
                    job_title=row.job_title,
                    wage_from=row.wage_from,
                    wage_unit=row.wage_unit,
                    wage_annualized=wage_annual,
                    prevailing_wage=row.prevailing_wage,
                    pw_unit=row.pw_unit,
                    pw_annualized=pw_annual,
                    wage_ratio=ratio,
                    worksite_city=row.worksite_city,
                    worksite_state=row.worksite_state,
                    worksite_zip=row.worksite_zip,
                    secondary_entity=row.secondary_entity,
                    total_workers=row.total_workers,
                    visa_class=row.visa_class,
                    received_date=row.received_date,
                    decision_date=row.decision_date,
                    fiscal_year=fiscal_year,
                )
            )
            if emp is not None:
                emp.total_lca_count += 1
            rows_out += 1
        run.rows_out = rows_out
    return rows_out
