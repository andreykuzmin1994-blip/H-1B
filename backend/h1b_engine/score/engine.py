"""Scoring engine entry points."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer
from h1b_engine.score.detectors import (
    compute_address_clusters,
    compute_naics_soc_frequency,
    compute_national_soc_medians,
    compute_soc_denial_rates,
    compute_violator_employer_ids,
    detect_for_employer,
    persist_flags,
)

log = logging.getLogger(__name__)


def score_all(employer_ids: Iterable[int] | None = None, min_filings: int = 0) -> int:
    """Score every employer (or a subset) and return how many were updated."""
    with get_session() as session:
        log.info("Building scoring context...")
        naics_soc_freq = compute_naics_soc_frequency(session)
        address_clusters = compute_address_clusters(session)
        soc_medians = compute_national_soc_medians(session)
        soc_denial_rates = compute_soc_denial_rates(session)
        violator_ids = compute_violator_employer_ids(session)
        log.info(
            "Context: %d NAICS, %d address clusters, %d SOC medians, %d violators",
            len(naics_soc_freq),
            len(address_clusters),
            len(soc_medians),
            len(violator_ids),
        )

        stmt = select(Employer)
        if employer_ids is not None:
            stmt = stmt.where(Employer.id.in_(list(employer_ids)))
        if min_filings:
            stmt = stmt.where(Employer.total_lca_count >= min_filings)

        count = 0
        for employer in session.scalars(stmt):
            outputs = detect_for_employer(
                session,
                employer,
                naics_soc_freq=naics_soc_freq,
                address_clusters=address_clusters,
                soc_medians=soc_medians,
                soc_denial_rates=soc_denial_rates,
                violator_ids=violator_ids,
            )
            persist_flags(session, employer, outputs)
            count += 1
    log.info("Scoring complete: %d employers scored", count)
    return count


def score_employer(employer_id: int) -> float:
    """Score a single employer by id. Returns the final anomaly_score."""
    score_all([employer_id])
    with get_session() as session:
        emp = session.get(Employer, employer_id)
        return float(emp.anomaly_score) if emp else 0.0


def export_high_risk(path: Path, min_score: float = 50, fmt: str = "csv") -> int:
    """Export employers above ``min_score`` to CSV/JSON."""
    with get_session() as session:
        rows = (
            session.execute(
                select(Employer)
                .where(Employer.anomaly_score >= min_score)
                .order_by(Employer.anomaly_score.desc())
            )
            .scalars()
            .all()
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        with path.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                ["id", "name", "state", "naics", "anomaly_score", "total_lca_count"]
            )
            for e in rows:
                writer.writerow(
                    [
                        e.id,
                        e.name,
                        e.state,
                        e.naics_code,
                        float(e.anomaly_score),
                        e.total_lca_count,
                    ]
                )
    elif fmt == "json":
        import json

        with path.open("w") as fh:
            json.dump(
                [
                    {
                        "id": e.id,
                        "name": e.name,
                        "state": e.state,
                        "naics": e.naics_code,
                        "anomaly_score": float(e.anomaly_score),
                        "total_lca_count": e.total_lca_count,
                    }
                    for e in rows
                ],
                fh,
                indent=2,
            )
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    log.info("Exported %d high-risk employers to %s", len(rows), path)
    return len(rows)
