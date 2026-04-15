"""Shared helpers used across ingestion sources."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from sqlalchemy.orm import Session

from h1b_engine.db import get_session
from h1b_engine.db.models import IngestionRun


# File extensions we recognise as raw ingestion input. Parquet is strongly
# preferred for large files: the DOL OFLC LCA quarterly dumps compress 5-10x
# smaller than CSV and load much faster. See scripts/download_data.py for the
# CSV -> Parquet conversion helper.
TABULAR_SUFFIXES: tuple[str, ...] = (".parquet", ".csv", ".xlsx", ".xls")


def data_dir() -> Path:
    base = Path(os.environ.get("DATA_DIR", "./data"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "raw").mkdir(exist_ok=True)
    (base / "cache").mkdir(exist_ok=True)
    return base


def read_table(path: Path, **kwargs: Any) -> pd.DataFrame:
    """Read a tabular data file as a DataFrame.

    Dispatches on file extension so ingest modules can accept Parquet, CSV, or
    Excel interchangeably. Parquet is the recommended format for large inputs
    (columnar + compressed, typically 5-10x smaller than CSV). ``dtype=object``
    is applied to CSV/Excel by default to match the legacy row-normalization
    code, which does its own per-field coercion.
    """
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        # Parquet preserves dtypes; callers that expect strings should coerce.
        return pd.read_parquet(path, **kwargs)
    if suffix in {".xlsx", ".xls"}:
        kwargs.setdefault("dtype", object)
        return pd.read_excel(path, **kwargs)
    if suffix == ".csv":
        kwargs.setdefault("dtype", object)
        kwargs.setdefault("low_memory", False)
        return pd.read_csv(path, **kwargs)
    raise ValueError(f"Unsupported tabular file format: {path.suffix} ({path})")


@contextmanager
def ingestion_run(source: str, params: dict | None = None) -> Iterator[tuple[Session, IngestionRun]]:
    """Open a session and record an IngestionRun row around the work.

    On success, marks the existing run row as ``success``.
    On failure, rolls back any in-flight data changes, then updates the SAME
    run row in place to ``failed`` and re-raises. Exactly one IngestionRun
    row per call either way.
    """
    with get_session() as session:
        run = IngestionRun(source=source, params=params, status="running")
        session.add(run)
        session.flush()
        try:
            yield session, run
            run.finished_at = datetime.utcnow()
            run.status = "success"
        except Exception as exc:
            session.rollback()
            run.status = "failed"
            run.finished_at = datetime.utcnow()
            run.error = str(exc)[:2000]
            session.add(run)
            session.commit()
            raise


def chunked(iterable, size: int):
    """Yield successive ``size``-sized chunks from ``iterable``."""
    batch: list = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
