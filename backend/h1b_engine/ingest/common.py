"""Shared helpers used across ingestion sources."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy.orm import Session

from h1b_engine.db import get_session
from h1b_engine.db.models import IngestionRun


def data_dir() -> Path:
    base = Path(os.environ.get("DATA_DIR", "./data"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "raw").mkdir(exist_ok=True)
    (base / "cache").mkdir(exist_ok=True)
    return base


@contextmanager
def ingestion_run(source: str, params: dict | None = None) -> Iterator[tuple[Session, IngestionRun]]:
    """Open a session and record an IngestionRun row around the work."""
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
            # Re-open a small session to mark failure
            with get_session() as s2:
                failed = IngestionRun(
                    source=source,
                    params=params,
                    status="failed",
                    finished_at=datetime.utcnow(),
                    error=str(exc)[:2000],
                )
                s2.add(failed)
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
