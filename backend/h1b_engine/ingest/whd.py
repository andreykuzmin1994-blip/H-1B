"""DOL Wage and Hour Division (WHD) enforcement data ingestion.

Source: https://enforcedata.dol.gov/views/data_summary.php

We also expose a DOL Data Portal API fetcher at apiprod.dol.gov/v4/ for
incremental updates between bulk file downloads.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import select

from h1b_engine.db.models import Employer, Violation
from h1b_engine.ingest.common import ingestion_run
from h1b_engine.utils import normalize_employer_name

log = logging.getLogger(__name__)

H1B_KEYWORDS = ("H1B", "H-1B", "INA", "IMMIGRATION AND NATIONALITY")


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


def _coerce_date(value) -> date | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value, errors="coerce").date()
    except Exception:
        return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _is_h1b_related(row: dict) -> bool:
    for _, val in row.items():
        if val is None:
            continue
        try:
            if pd.isna(val):
                continue
        except TypeError:
            pass
        text = str(val).upper()
        for kw in H1B_KEYWORDS:
            if kw in text:
                return True
    return False


def ingest_file(path: Path, h1b_only: bool = True) -> int:
    frame = pd.read_csv(path, dtype=object, low_memory=False)
    frame.columns = [str(c).strip().upper() for c in frame.columns]
    rows_out = 0

    with ingestion_run("whd_enforcement", {"file": str(path), "h1b_only": h1b_only}) as (
        session,
        run,
    ):
        for raw in frame.to_dict(orient="records"):
            if h1b_only and not _is_h1b_related(raw):
                continue
            employer_name = _str(raw.get("LEGAL_NAME")) or _str(raw.get("TRADE_NM")) or _str(
                raw.get("EMPLOYER_NAME")
            )
            if not employer_name:
                continue
            state = _str(raw.get("ST_CD")) or _str(raw.get("STATE"))
            name_norm = normalize_employer_name(employer_name)
            employer = None
            if state:
                employer = session.execute(
                    select(Employer).where(
                        Employer.name_normalized == name_norm,
                        Employer.state == state,
                    )
                ).scalar_one_or_none()

            violation = Violation(
                employer_id=employer.id if employer else None,
                employer_name_raw=employer_name,
                source="WHD_ENFORCEMENT",
                violation_type=_str(raw.get("ACT_ID_DESC")) or _str(raw.get("VIOLATION_TYPE")),
                violation_date=_coerce_date(
                    raw.get("FINDINGS_END_DATE") or raw.get("CONCLUSION_DATE")
                ),
                back_wages_amount=_coerce_float(raw.get("BW_ATP_AMT") or raw.get("BACK_WAGES")),
                penalty_amount=_coerce_float(raw.get("CMP_ASSD_AMT") or raw.get("PENALTY")),
                description=_str(raw.get("CASE_VIOLTN_CNT_DESC"))
                or _str(raw.get("DESCRIPTION")),
                source_url="https://enforcedata.dol.gov/",
            )
            session.add(violation)
            rows_out += 1

        run.rows_in = len(frame)
        run.rows_out = rows_out
    log.info("WHD ingest complete: %d violations inserted", rows_out)
    return rows_out


def fetch_incremental(base_url: str, since: date | None = None) -> list[dict]:
    """Fetch new enforcement actions from the DOL Data Portal API.

    No API key required. Returns a list of raw records.
    """
    params: dict[str, str] = {}
    if since:
        params["format"] = "json"
        params["filter"] = f"findings_end_date >= '{since.isoformat()}'"
    resp = requests.get(f"{base_url}/get/whisard/whisard/", params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data", payload if isinstance(payload, list) else [])
