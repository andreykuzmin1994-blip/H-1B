#!/usr/bin/env python
"""End-to-end smoke test using synthetic fixtures.

Runs the full pipeline (ingest -> score -> graph -> score) against a throw-away
SQLite database so you can verify the wiring without Postgres or real data.

    python scripts/smoke_test.py          # uses ./data/smoke.db
    python scripts/smoke_test.py --db /tmp/smoke.db --keep

Fixtures live under ``data/fixtures/smoke/``. The BLS OEWS ingester is
Excel-only, so its CSV fixture is converted to a one-sheet xlsx at runtime.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_BACKEND))


def _csv_to_xlsx(src: Path, dst: Path) -> None:
    """Convert a CSV to a single-sheet xlsx (BLS ingester requires Excel)."""
    import csv

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    with src.open() as fh:
        for row in csv.reader(fh):
            ws.append(row)
    wb.save(dst)


def _bootstrap_schema() -> None:
    from h1b_engine.db import base, models  # noqa: F401 - register models

    base.Base.metadata.drop_all(base.get_engine())
    base.Base.metadata.create_all(base.get_engine())


def _run(db_path: Path, keep: bool) -> int:
    fixtures = REPO_BACKEND / "data" / "fixtures" / "smoke"
    if not fixtures.exists():
        print(f"[FAIL] smoke fixtures not found at {fixtures}", file=sys.stderr)
        return 2

    # Point the app at a fresh SQLite file.
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"

    stage = REPO_BACKEND / "data" / "_smoke_stage"
    if stage.exists():
        shutil.rmtree(stage)
    for sub in ("lca", "uscis_hub", "whd", "bls", "warn"):
        (stage / "raw" / sub).mkdir(parents=True, exist_ok=True)
    os.environ["DATA_DIR"] = str(stage)

    # Copy / convert fixtures into the staging directory.
    shutil.copy(fixtures / "lca.csv", stage / "raw" / "lca" / "lca_smoke_2024.csv")
    shutil.copy(
        fixtures / "uscis_hub_2024.csv",
        stage / "raw" / "uscis_hub" / "uscis_hub_2024.csv",
    )
    shutil.copy(fixtures / "whd.csv", stage / "raw" / "whd" / "whd_smoke.csv")
    shutil.copy(fixtures / "warn.csv", stage / "raw" / "warn" / "warn_smoke.csv")
    _csv_to_xlsx(
        fixtures / "bls_oews_2024.csv",
        stage / "raw" / "bls" / "national_M2024_dl.xlsx",
    )

    print(f"[smoke] DATABASE_URL={os.environ['DATABASE_URL']}")
    print(f"[smoke] DATA_DIR={stage}")

    _bootstrap_schema()

    # Imports are done after env setup so modules pick up the SQLite URL.
    from sqlalchemy import func, select

    from h1b_engine.db import get_session
    from h1b_engine.db.models import (
        AnomalyFlag,
        Employer,
        EntityRelationship,
        LayoffEvent,
        LcaFiling,
        SocWageBenchmark,
        UscisEmployerStats,
        Violation,
    )
    from h1b_engine.graph.builder import build_all
    from h1b_engine.ingest import bls_oews, lca, uscis_hub, warn, whd
    from h1b_engine.score.engine import score_all

    print("\n== ingest ==")
    n = lca.ingest_file(stage / "raw" / "lca" / "lca_smoke_2024.csv", fiscal_year=2024)
    print(f"  lca: {n} filings")
    n = uscis_hub.ingest_file(
        stage / "raw" / "uscis_hub" / "uscis_hub_2024.csv", fiscal_year=2024
    )
    print(f"  uscis_hub: {n} rows")
    n = whd.ingest_file(stage / "raw" / "whd" / "whd_smoke.csv", h1b_only=True)
    print(f"  whd: {n} violations")
    n = warn.ingest_file(stage / "raw" / "warn" / "warn_smoke.csv", default_state="GA")
    print(f"  warn: {n} layoff events")
    n = bls_oews.ingest_file(
        stage / "raw" / "bls" / "national_M2024_dl.xlsx",
        year=2024,
        area_type="NATIONAL",
    )
    print(f"  bls_oews: {n} benchmarks")

    print("\n== score (pass 1) ==")
    n = score_all()
    print(f"  {n} employers scored")

    print("\n== graph build ==")
    counts = build_all()
    for rtype, count in counts.items():
        print(f"  {rtype}: {count}")

    print("\n== score (pass 2 - picks up CONNECTED_TO_VIOLATOR) ==")
    n = score_all()
    print(f"  {n} employers scored")

    print("\n== DB totals ==")
    with get_session() as session:
        tables = [
            ("employers", Employer),
            ("lca_filings", LcaFiling),
            ("uscis_employer_stats", UscisEmployerStats),
            ("violations", Violation),
            ("layoff_events", LayoffEvent),
            ("soc_wage_benchmarks", SocWageBenchmark),
            ("anomaly_flags", AnomalyFlag),
            ("entity_relationships", EntityRelationship),
        ]
        for label, model in tables:
            count = session.execute(select(func.count()).select_from(model)).scalar_one()
            print(f"  {label:24s} {count}")

        print("\n== top employers by anomaly_score ==")
        ranked = session.execute(
            select(Employer.name, Employer.state, Employer.anomaly_score)
            .order_by(Employer.anomaly_score.desc())
            .limit(10)
        ).all()
        for name, state, score in ranked:
            print(f"  {score:>6.2f}  {state}  {name}")

        print("\n== flags ==")
        flags = session.execute(
            select(
                AnomalyFlag.flag_type,
                AnomalyFlag.flag_severity,
                Employer.name,
            ).join(Employer, AnomalyFlag.employer_id == Employer.id)
        ).all()
        for flag_type, severity, name in flags:
            print(f"  [{severity or '-':<8}] {flag_type:32s}  {name}")

    if not keep:
        shutil.rmtree(stage)
        if db_path.exists():
            db_path.unlink()
        print(f"\n[smoke] cleaned up {stage} and {db_path}")
    else:
        print(f"\n[smoke] kept staging dir {stage} and db {db_path}")

    print("\n[smoke] OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        type=Path,
        default=REPO_BACKEND / "data" / "smoke.db",
        help="SQLite database file to use (created fresh each run).",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the staging directory and SQLite file after the run.",
    )
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    if args.db.exists():
        args.db.unlink()
    return _run(args.db, args.keep)


if __name__ == "__main__":
    sys.exit(main())
