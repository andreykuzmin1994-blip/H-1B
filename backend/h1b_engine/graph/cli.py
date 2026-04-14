"""Entity graph CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from h1b_engine.graph.builder import (
    build_address_links,
    build_agent_links,
    build_all,
    build_name_variants,
    build_officer_links,
    subgraph_for_employer,
)
from h1b_engine.utils.logging import setup_logging

app = typer.Typer(help="H-1B entity graph CLI")
console = Console()


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging("DEBUG" if verbose else "INFO")


@app.command("build-address-links")
def build_address() -> None:
    n = build_address_links()
    console.print(f"[green]Added[/green] {n} shared-address relationships.")


@app.command("build-agent-links")
def build_agent() -> None:
    n = build_agent_links()
    console.print(f"[green]Added[/green] {n} shared-agent relationships.")


@app.command("build-officer-links")
def build_officer() -> None:
    n = build_officer_links()
    console.print(f"[green]Added[/green] {n} shared-officer relationships.")


@app.command("build-name-variants")
def build_variants(threshold: float = typer.Option(85.0, "--threshold", "-t")) -> None:
    n = build_name_variants(threshold=threshold)
    console.print(f"[green]Added[/green] {n} name-variant relationships.")


@app.command("build-all")
def build_all_cmd() -> None:
    counts = build_all()
    for rtype, n in counts.items():
        console.print(f"[green]{rtype}:[/green] {n}")


@app.command("visualize")
def visualize(
    employer_id: int = typer.Option(..., "--employer-id"),
    depth: int = typer.Option(2, "--depth"),
    out: Optional[Path] = typer.Option(None, "--out", "-o"),
) -> None:
    """Export a subgraph for an employer as JSON (for the frontend graph view)."""
    graph = subgraph_for_employer(employer_id, max_depth=depth)
    payload = json.dumps(graph, indent=2)
    if out:
        out.write_text(payload)
        console.print(f"[green]Wrote {len(graph['nodes'])} nodes to {out}[/green]")
    else:
        console.print(payload)


if __name__ == "__main__":
    app()
