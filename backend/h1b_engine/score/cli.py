"""CLI for the scoring engine."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from h1b_engine.score.engine import export_high_risk, score_all, score_employer
from h1b_engine.utils.logging import setup_logging

app = typer.Typer(help="H-1B anomaly scoring CLI")
console = Console()


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging("DEBUG" if verbose else "INFO")


@app.command()
def run(
    employer_id: Optional[int] = typer.Option(None, "--employer-id"),
    min_filings: int = typer.Option(0, "--min-filings"),
) -> None:
    """Score all employers (or a specific one)."""
    if employer_id is not None:
        score = score_employer(employer_id)
        console.print(f"[green]Employer {employer_id}:[/green] score={score}")
    else:
        n = score_all(min_filings=min_filings)
        console.print(f"[green]Scoring complete.[/green] {n} employers updated.")


@app.command()
def refresh() -> None:
    """Re-score all employers (alias for `run`)."""
    n = score_all()
    console.print(f"[green]Rescored {n} employers.[/green]")


@app.command()
def export(
    out: Path = typer.Option(Path("reports/high_risk.csv"), "--out", "-o"),
    min_score: float = typer.Option(50, "--min-score"),
    fmt: str = typer.Option("csv", "--format"),
) -> None:
    """Export employers above a score threshold."""
    n = export_high_risk(out, min_score=min_score, fmt=fmt)
    console.print(f"[green]Exported {n} employers to {out}[/green]")


if __name__ == "__main__":
    app()
