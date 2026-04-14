"""Investigation CLI."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from sqlalchemy import select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer
from h1b_engine.investigate.report import generate_report, tip_text
from h1b_engine.utils.logging import setup_logging

app = typer.Typer(help="H-1B investigation CLI")
console = Console()


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging("DEBUG" if verbose else "INFO")


@app.command()
def run(
    employer_id: Optional[int] = typer.Option(None, "--employer-id"),
    min_score: Optional[float] = typer.Option(None, "--min-score"),
    output: str = typer.Option("report", "--output", help="report|tip"),
    out_dir: Path = typer.Option(Path("reports"), "--out-dir"),
    fmt: str = typer.Option("txt", "--format"),
) -> None:
    """Generate an investigation report (or tip text) for an employer."""
    ids: list[int] = []
    if employer_id is not None:
        ids.append(employer_id)
    elif min_score is not None:
        with get_session() as session:
            ids = [
                r[0]
                for r in session.execute(
                    select(Employer.id).where(Employer.anomaly_score >= min_score)
                ).all()
            ]
    else:
        console.print("[red]Provide --employer-id or --min-score[/red]")
        raise typer.Exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    for eid in ids:
        if output == "report":
            text = generate_report(eid)
        else:
            text = tip_text(eid)
        out_path = out_dir / f"employer_{eid}.{fmt}"
        out_path.write_text(text)
        console.print(f"[green]Wrote[/green] {out_path}")


if __name__ == "__main__":
    app()
