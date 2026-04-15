#!/usr/bin/env python
"""Download public raw data and (optionally) convert it to Parquet.

Large public-source dumps (DOL OFLC LCA, USCIS Hub, BLS OEWS, WHD) are too big
to commit to GitHub. Instead we keep them out of git (see .gitignore) and let
each contributor fetch them on demand into ``backend/data/raw/<source>/``.

Two commands are provided:

* ``fetch`` - stream a URL to disk without loading it into memory. Use this
  when a URL is known (CLI flag or manual URL from the DOL page).
* ``to-parquet`` - convert a CSV or Excel file in place to Parquet with
  Snappy compression. Typical shrink factor on DOL LCA data is 5-10x, so a
  ~3 GB CSV becomes ~300 MB of Parquet that ingest_file() reads natively.

Examples
--------

    # Fetch an LCA quarterly file (substitute the real URL from the DOL page)
    python scripts/download_data.py fetch \\
        --url https://www.dol.gov/sites/dolgov/files/ETA/oflc/pdfs/LCA_Disclosure_Data_FY2024_Q1.csv \\
        --source lca

    # Shrink any CSV to Parquet (keeps the original unless --replace is given)
    python scripts/download_data.py to-parquet \\
        --path backend/data/raw/lca/LCA_Disclosure_Data_FY2024_Q1.csv

    # Discover every CSV/XLSX under backend/data/raw and convert all of them
    python scripts/download_data.py to-parquet --all
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

# Allow running from scripts/ without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h1b_engine.ingest.common import TABULAR_SUFFIXES, data_dir  # noqa: E402

app = typer.Typer(help="Fetch + convert raw data files for the H-1B engine")
console = Console()


# Source -> subdirectory under data/raw. Keep in sync with cli.py defaults.
SOURCE_DIRS: dict[str, str] = {
    "lca": "lca",
    "uscis": "uscis_hub",
    "uscis-hub": "uscis_hub",
    "whd": "whd",
    "bls": "bls",
    "warn": "warn",
}


def _resolve_dest(source: str, filename: str) -> Path:
    subdir = SOURCE_DIRS.get(source.lower())
    if not subdir:
        raise typer.BadParameter(
            f"Unknown source '{source}'. Known: {sorted(SOURCE_DIRS)}"
        )
    target_dir = data_dir() / "raw" / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def _stream_download(url: str, dest: Path, chunk_size: int = 1 << 20) -> int:
    """Stream-download ``url`` to ``dest``. Returns bytes written.

    Uses requests with ``stream=True`` so we never buffer a multi-GB body in
    memory. Writes into a ``.part`` sidecar and renames on success so a crashed
    download never masquerades as a complete file.
    """
    import requests  # deferred import; heavy dep

    part = dest.with_suffix(dest.suffix + ".part")
    total = 0
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with open(part, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                total += len(chunk)
    part.replace(dest)
    return total


@app.command("fetch")
def fetch_cmd(
    url: str = typer.Option(..., "--url", "-u", help="Direct URL to the raw file"),
    source: str = typer.Option(
        ..., "--source", "-s", help=f"One of: {', '.join(sorted(SOURCE_DIRS))}"
    ),
    filename: Optional[str] = typer.Option(
        None, "--filename", "-f", help="Override the saved filename"
    ),
    convert: bool = typer.Option(
        False,
        "--convert/--no-convert",
        help="Convert to Parquet after download (CSV/Excel only)",
    ),
    replace: bool = typer.Option(
        False, "--replace", help="With --convert, delete the original after conversion"
    ),
) -> None:
    """Stream-download a raw data file into data/raw/<source>/."""
    name = filename or url.rstrip("/").rsplit("/", 1)[-1]
    dest = _resolve_dest(source, name)
    console.print(f"[cyan]Fetching[/cyan] {url}")
    console.print(f"  -> {dest}")
    nbytes = _stream_download(url, dest)
    console.print(f"[green]Saved[/green] {nbytes/1e6:.1f} MB")

    if convert and dest.suffix.lower() in {".csv", ".xlsx", ".xls"}:
        _convert_one(dest, replace=replace)


def _convert_one(path: Path, replace: bool = False) -> Path:
    """Convert a single CSV/Excel file to Parquet next to the original."""
    import pandas as pd

    suffix = path.suffix.lower()
    if suffix == ".parquet":
        console.print(f"[yellow]Skip[/yellow] {path.name} (already Parquet)")
        return path
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise typer.BadParameter(f"Cannot convert {path.suffix} to Parquet")

    out = path.with_suffix(".parquet")
    console.print(f"[cyan]Converting[/cyan] {path.name} -> {out.name}")
    if suffix == ".csv":
        frame = pd.read_csv(path, dtype=object, low_memory=False)
    else:
        frame = pd.read_excel(path, dtype=object)
    # Normalize columns to strings so Parquet's schema is stable across files.
    frame.columns = [str(c) for c in frame.columns]
    frame.to_parquet(out, compression="snappy", index=False)

    src_size = path.stat().st_size
    out_size = out.stat().st_size
    ratio = src_size / out_size if out_size else 0
    console.print(
        f"  {src_size/1e6:.1f} MB -> {out_size/1e6:.1f} MB ({ratio:.1f}x smaller)"
    )
    if replace:
        path.unlink()
        console.print(f"[yellow]Removed[/yellow] {path.name}")
    return out


@app.command("to-parquet")
def to_parquet_cmd(
    path: Optional[Path] = typer.Option(None, "--path", "-p"),
    all_: bool = typer.Option(False, "--all", help="Convert every CSV/XLSX under data/raw"),
    replace: bool = typer.Option(
        False, "--replace", help="Delete the original CSV/XLSX after successful conversion"
    ),
) -> None:
    """Convert CSV or Excel files to Snappy-compressed Parquet."""
    if not path and not all_:
        raise typer.BadParameter("Pass --path <file> or --all")

    targets: list[Path] = []
    if path:
        targets.append(path)
    if all_:
        base = data_dir() / "raw"
        for suffix in TABULAR_SUFFIXES:
            if suffix == ".parquet":
                continue
            targets.extend(base.rglob(f"*{suffix}"))

    if not targets:
        console.print("[yellow]Nothing to convert[/yellow]")
        raise typer.Exit(0)

    for p in sorted(set(targets)):
        _convert_one(p, replace=replace)
    console.print("[green]Done.[/green]")


if __name__ == "__main__":
    app()
