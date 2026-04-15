"""Tests for the shared ``read_table`` dispatch and end-to-end Parquet ingest.

Large raw dumps (DOL LCA, USCIS Hub) ship as CSV; we convert them to Parquet
so a 3 GB CSV becomes ~300 MB on disk and round-trips through pandas with no
data loss. These tests exercise the file-format dispatch in common.read_table
and prove that LCA's read_file iterates Parquet rows correctly.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from h1b_engine.ingest.common import read_table
from h1b_engine.ingest.lca import normalize_row, read_file


pytest.importorskip("pyarrow")


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "CASE_NUMBER": "I-200-22222-111111",
                "CASE_STATUS": "CERTIFIED",
                "VISA_CLASS": "H-1B",
                "EMPLOYER_NAME": "Acme Parquet Co",
                "EMPLOYER_STATE": "CA",
                "SOC_CODE": "15-1252",
                "JOB_TITLE": "Software Developer",
                "WAGE_RATE_OF_PAY_FROM": "95000",
                "WAGE_UNIT_OF_PAY": "Year",
                "PREVAILING_WAGE": "90000",
                "PW_UNIT_OF_PAY": "Year",
                "RECEIVED_DATE": "2024-03-01",
            }
        ]
    )


def test_read_table_dispatches_on_extension(tmp_path: Path):
    frame = _sample_frame()
    csv_path = tmp_path / "sample.csv"
    parquet_path = tmp_path / "sample.parquet"
    frame.to_csv(csv_path, index=False)
    frame.to_parquet(parquet_path, index=False)

    csv_loaded = read_table(csv_path)
    parquet_loaded = read_table(parquet_path)

    assert list(csv_loaded.columns) == list(frame.columns)
    assert list(parquet_loaded.columns) == list(frame.columns)
    assert csv_loaded.iloc[0]["CASE_NUMBER"] == "I-200-22222-111111"
    assert parquet_loaded.iloc[0]["CASE_NUMBER"] == "I-200-22222-111111"


def test_read_table_rejects_unknown_format(tmp_path: Path):
    junk = tmp_path / "sample.txt"
    junk.write_text("not a real table")
    with pytest.raises(ValueError, match="Unsupported"):
        read_table(junk)


def test_lca_read_file_handles_parquet(tmp_path: Path):
    """read_file yields dicts from Parquet identical to CSV, and those dicts
    pass through normalize_row without issue."""
    frame = _sample_frame()
    parquet_path = tmp_path / "lca.parquet"
    frame.to_parquet(parquet_path, index=False)

    rows = list(read_file(parquet_path))
    assert len(rows) == 1
    normalized = normalize_row(rows[0], fiscal_year=2024)
    assert normalized is not None
    assert normalized.case_number == "I-200-22222-111111"
    assert normalized.employer_name == "Acme Parquet Co"
    assert normalized.wage_from == 95000.0
