"""BLS OEWS wage benchmark ingestion.

Source: https://www.bls.gov/oes/tables.htm

The national file (e.g. ``national_M2024_dl.xlsx``) contains median / mean /
percentile wage data for ~830 SOC codes. This is the benchmark dataset used for
wage anomaly detection.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from h1b_engine.db.models import SocWageBenchmark
from h1b_engine.ingest.common import ingestion_run, read_table

log = logging.getLogger(__name__)

COLUMN_MAP: dict[str, str] = {
    "OCC_CODE": "soc_code",
    "SOC_CODE": "soc_code",
    "OCC_TITLE": "soc_title",
    "TOT_EMP": "employment",
    "A_MEAN": "mean_annual_wage",
    "A_MEDIAN": "median_annual_wage",
    "A_PCT10": "pct10_annual_wage",
    "A_PCT25": "pct25_annual_wage",
    "A_PCT75": "pct75_annual_wage",
    "A_PCT90": "pct90_annual_wage",
    "AREA": "area_code",
    "AREA_TITLE": "area_name",
    "AREA_NAME": "area_name",
    "PRIM_STATE": "state_fips",
}


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, str):
        if value.strip() in {"", "*", "**", "#", "NA"}:
            return None
        value = value.replace(",", "").replace("$", "").strip()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _to_str(value) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    s = str(value).strip()
    return s or None


def ingest_file(path: Path, year: int, area_type: str = "NATIONAL") -> int:
    frame = read_table(path)
    frame.columns = [str(c).strip().upper() for c in frame.columns]

    rows_out = 0
    with ingestion_run(
        "bls_oews", {"file": str(path), "year": year, "area_type": area_type}
    ) as (session, run):
        for raw in frame.to_dict(orient="records"):
            canonical: dict = {}
            for key, value in raw.items():
                canon = COLUMN_MAP.get(key)
                if canon:
                    canonical[canon] = value

            soc_code = _to_str(canonical.get("soc_code"))
            if not soc_code:
                continue
            # OEWS publishes broad "major" roll-ups with codes ending in -0000.
            # Keep them, but they can be filtered later by callers.

            bench = SocWageBenchmark(
                soc_code=soc_code,
                soc_title=_to_str(canonical.get("soc_title")),
                oews_year=year,
                area_type=area_type.upper(),
                area_code=_to_str(canonical.get("area_code")),
                area_name=_to_str(canonical.get("area_name")),
                employment=_to_int(canonical.get("employment")),
                mean_annual_wage=_to_float(canonical.get("mean_annual_wage")),
                median_annual_wage=_to_float(canonical.get("median_annual_wage")),
                pct10_annual_wage=_to_float(canonical.get("pct10_annual_wage")),
                pct25_annual_wage=_to_float(canonical.get("pct25_annual_wage")),
                pct75_annual_wage=_to_float(canonical.get("pct75_annual_wage")),
                pct90_annual_wage=_to_float(canonical.get("pct90_annual_wage")),
            )
            session.add(bench)
            rows_out += 1
        run.rows_in = len(frame)
        run.rows_out = rows_out
    log.info("BLS OEWS ingest complete: %d benchmarks inserted (%s %d)", rows_out, area_type, year)
    return rows_out
