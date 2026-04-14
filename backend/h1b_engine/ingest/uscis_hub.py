"""USCIS H-1B Employer Data Hub ingestion.

Source: https://www.uscis.gov/archive/h-1b-employer-data-hub-files

Annual CSV/Excel files with approval/denial counts per employer.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from h1b_engine.db.models import Employer, UscisEmployerStats
from h1b_engine.ingest.common import ingestion_run
from h1b_engine.utils import normalize_employer_name

log = logging.getLogger(__name__)

COLUMN_MAP: dict[str, str] = {
    "EMPLOYER (PETITIONER) NAME": "employer_name",
    "EMPLOYER NAME": "employer_name",
    "PETITIONER NAME": "employer_name",
    "TAX ID": "tax_id",
    "EMPLOYER PETITIONER": "employer_name",
    "INITIAL APPROVAL": "initial_approvals",
    "INITIAL APPROVALS": "initial_approvals",
    "INITIAL DENIAL": "initial_denials",
    "INITIAL DENIALS": "initial_denials",
    "CONTINUING APPROVAL": "continuing_approvals",
    "CONTINUING APPROVALS": "continuing_approvals",
    "CONTINUING DENIAL": "continuing_denials",
    "CONTINUING DENIALS": "continuing_denials",
    "NAICS CODE": "naics_code",
    "NAICS": "naics_code",
    "PETITIONER CITY": "city",
    "CITY": "city",
    "PETITIONER STATE": "state",
    "STATE": "state",
    "PETITIONER ZIP CODE": "zip",
    "ZIP": "zip",
    "LINE BY LINE": "line_type",
    "FISCAL YEAR": "fiscal_year",
}


def _int(value) -> int:
    if value is None:
        return 0
    try:
        if pd.isna(value):
            return 0
    except TypeError:
        pass
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def _str(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    s = str(value).strip()
    return s or None


def ingest_file(path: Path, fiscal_year: int) -> int:
    """Ingest a USCIS Employer Data Hub file. Returns rows inserted."""
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, dtype=object)
    else:
        frame = pd.read_csv(path, dtype=object, low_memory=False)
    frame.columns = [str(c).strip().upper() for c in frame.columns]

    rows_out = 0
    with ingestion_run("uscis_hub", {"file": str(path), "fiscal_year": fiscal_year}) as (
        session,
        run,
    ):
        for raw in frame.to_dict(orient="records"):
            canonical: dict = {}
            for key, value in raw.items():
                canon = COLUMN_MAP.get(key)
                if canon:
                    canonical[canon] = value
            name = _str(canonical.get("employer_name"))
            if not name:
                continue

            tax_id = _str(canonical.get("tax_id"))
            tax_last4 = tax_id[-4:] if tax_id else None
            state = _str(canonical.get("state"))
            city = _str(canonical.get("city"))
            zip_ = _str(canonical.get("zip"))
            naics = _str(canonical.get("naics_code"))

            name_norm = normalize_employer_name(name)
            employer = None
            if state:
                employer = session.execute(
                    select(Employer).where(
                        Employer.name_normalized == name_norm,
                        Employer.state == state,
                    )
                ).scalar_one_or_none()

            stats = UscisEmployerStats(
                employer_id=employer.id if employer else None,
                employer_name_raw=name,
                tax_id_last4=tax_last4,
                fiscal_year=fiscal_year,
                initial_approvals=_int(canonical.get("initial_approvals")),
                initial_denials=_int(canonical.get("initial_denials")),
                continuing_approvals=_int(canonical.get("continuing_approvals")),
                continuing_denials=_int(canonical.get("continuing_denials")),
                city=city,
                state=state,
                zip=zip_,
                naics_code=naics[:6] if naics else None,
            )
            session.add(stats)
            rows_out += 1
        run.rows_in = len(frame)
        run.rows_out = rows_out
    log.info("USCIS hub ingest complete: %d rows inserted", rows_out)
    return rows_out
