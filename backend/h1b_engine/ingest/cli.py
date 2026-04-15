"""Typer-based CLI for data ingestion."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from h1b_engine.ingest import (
    bls_oews,
    geocode,
    lca,
    opencorporates,
    uscis_hub,
    warn,
    whd,
    willful_violators,
)
from h1b_engine.ingest.common import TABULAR_SUFFIXES, data_dir
from h1b_engine.utils.logging import setup_logging


def _globs(base: Path, recursive: bool = False) -> list[Path]:
    """Return all tabular files under ``base`` sorted by name."""
    globber = base.rglob if recursive else base.glob
    results: list[Path] = []
    for suffix in TABULAR_SUFFIXES:
        results.extend(globber(f"*{suffix}"))
    return sorted(results)

app = typer.Typer(help="H-1B Transparency Engine ingestion CLI")
console = Console()


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging("DEBUG" if verbose else "INFO")


@app.command("lca")
def lca_cmd(
    fiscal_year: Optional[int] = typer.Option(None, "--fiscal-year", "-y"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Path to a specific LCA file"),
    directory: Optional[Path] = typer.Option(
        None, "--dir", "-d", help="Directory of LCA files (ingests everything inside)"
    ),
) -> None:
    """Ingest DOL OFLC LCA disclosure data."""
    files: list[Path] = []
    if path:
        files.append(path)
    elif directory:
        files.extend(_globs(directory))
    else:
        base = data_dir() / "raw" / "lca"
        if not base.exists():
            console.print(f"[yellow]No LCA files found. Drop files into {base}[/yellow]")
            raise typer.Exit(1)
        files.extend(_globs(base))

    if not files:
        console.print("[red]No LCA files to ingest[/red]")
        raise typer.Exit(1)

    total = 0
    for f in files:
        console.print(f"[cyan]Ingesting[/cyan] {f.name}")
        total += lca.ingest_file(f, fiscal_year=fiscal_year)
    console.print(f"[green]Done.[/green] {total} LCA filings inserted.")


@app.command("uscis-hub")
def uscis_hub_cmd(
    fiscal_year: int = typer.Option(..., "--fiscal-year", "-y"),
    path: Optional[Path] = typer.Option(None, "--path", "-p"),
) -> None:
    """Ingest USCIS H-1B Employer Data Hub file."""
    if not path:
        base = data_dir() / "raw" / "uscis_hub"
        candidates: list[Path] = []
        for suffix in TABULAR_SUFFIXES:
            candidates.extend(base.glob(f"*{fiscal_year}*{suffix}"))
        if not candidates:
            console.print(f"[red]No USCIS file found for FY{fiscal_year} in {base}[/red]")
            raise typer.Exit(1)
        path = sorted(candidates)[0]
    n = uscis_hub.ingest_file(path, fiscal_year=fiscal_year)
    console.print(f"[green]USCIS hub ingest complete.[/green] {n} rows.")


@app.command("whd-enforcement")
def whd_enforcement_cmd(
    path: Optional[Path] = typer.Option(None, "--path", "-p"),
    h1b_only: bool = typer.Option(True, "--h1b-only/--all"),
) -> None:
    """Ingest DOL WHD enforcement CSV."""
    if not path:
        base = data_dir() / "raw" / "whd"
        candidates = _globs(base)
        if not candidates:
            console.print(f"[red]No WHD files found in {base}[/red]")
            raise typer.Exit(1)
        path = candidates[0]
    n = whd.ingest_file(path, h1b_only=h1b_only)
    console.print(f"[green]WHD ingest complete.[/green] {n} violations.")


@app.command("violators")
def violators_cmd(
    url: Optional[str] = typer.Option(None, "--url", "-u"),
) -> None:
    """Scrape the DOL Willful Violator list."""
    n = willful_violators.ingest(url=url) if url else willful_violators.ingest()
    console.print(f"[green]Willful violator ingest complete.[/green] {n} records.")


@app.command("bls-oews")
def bls_oews_cmd(
    year: int = typer.Option(..., "--year", "-y"),
    path: Optional[Path] = typer.Option(None, "--path", "-p"),
    area_type: str = typer.Option("NATIONAL", "--area-type"),
) -> None:
    """Ingest BLS OEWS wage benchmark file (Excel)."""
    if not path:
        base = data_dir() / "raw" / "bls"
        candidates: list[Path] = []
        for suffix in TABULAR_SUFFIXES:
            candidates.extend(base.glob(f"*{year}*{suffix}"))
        if not candidates:
            console.print(f"[red]No BLS OEWS file found for {year} in {base}[/red]")
            raise typer.Exit(1)
        path = sorted(candidates)[0]
    n = bls_oews.ingest_file(path, year=year, area_type=area_type)
    console.print(f"[green]BLS OEWS ingest complete.[/green] {n} benchmarks.")


@app.command("geocode")
def geocode_cmd(
    limit: Optional[int] = typer.Option(None, "--limit"),
    only_missing: bool = typer.Option(True, "--only-missing/--all"),
) -> None:
    """Geocode and classify employer addresses."""
    n = geocode.run_batch(limit=limit, only_missing=only_missing)
    console.print(f"[green]Geocode/classify complete.[/green] {n} employers updated.")


@app.command("classify-addresses")
def classify_addresses_cmd(
    limit: Optional[int] = typer.Option(None, "--limit"),
    only_missing: bool = typer.Option(True, "--only-missing/--all"),
) -> None:
    """Alias for `geocode` — kept for parity with the spec's CLI examples."""
    geocode_cmd(limit=limit, only_missing=only_missing)


@app.command("warn")
def warn_cmd(
    path: Optional[Path] = typer.Option(
        None, "--path", "-p", help="Single WARN CSV/XLSX file"
    ),
    directory: Optional[Path] = typer.Option(
        None, "--dir", "-d", help="Directory of WARN files (one or more states)"
    ),
    state: Optional[str] = typer.Option(
        None, "--state", "-s", help="2-letter state code for a single-state file"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Source tag override (e.g. LAYOFFS_FYI, WARN_FEDERAL)",
    ),
    source_url: Optional[str] = typer.Option(None, "--source-url"),
) -> None:
    """Ingest WARN Act mass-layoff notices (state or federal) or Layoffs.fyi CSV.

    Default layout: drop state files in ``data/raw/warn/<state>/*.csv`` and the
    command will walk the tree, tagging each file with ``WARN_STATE_<XX>``.
    """
    files: list[tuple[Path, str | None]] = []
    if path:
        files.append((path, state.upper() if state else None))
    elif directory:
        for f in _globs(directory, recursive=True):
            inferred = state or (f.parent.name.upper() if len(f.parent.name) == 2 else None)
            files.append((f, inferred))
    else:
        base = data_dir() / "raw" / "warn"
        if not base.exists():
            console.print(f"[yellow]No WARN files found. Drop files into {base}[/yellow]")
            raise typer.Exit(1)
        for f in _globs(base, recursive=True):
            inferred = f.parent.name.upper() if len(f.parent.name) == 2 else None
            files.append((f, inferred))

    if not files:
        console.print("[red]No WARN files to ingest[/red]")
        raise typer.Exit(1)

    total = 0
    for f, inferred_state in files:
        console.print(f"[cyan]Ingesting[/cyan] {f.name} (state={inferred_state or '-'})")
        total += warn.ingest_file(
            f,
            source=source,
            default_state=inferred_state,
            source_url=source_url,
        )
    console.print(f"[green]WARN ingest complete.[/green] {total} layoff events inserted.")


@app.command("opencorporates")
def opencorporates_cmd(
    limit: Optional[int] = typer.Option(None, "--limit"),
    only_missing: bool = typer.Option(True, "--only-missing/--all"),
) -> None:
    """Enrich employers with OpenCorporates entity data."""
    n = opencorporates.run_batch(limit=limit, only_missing=only_missing)
    console.print(f"[green]OpenCorporates enrichment complete.[/green] {n} employers.")


if __name__ == "__main__":
    app()
