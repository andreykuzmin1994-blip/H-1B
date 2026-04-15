"""Personnel Look-Up CLI."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from h1b_engine.credentials.lookup import (
    PersonnelReport,
    bootstrap,
    lookup_by_name,
    lookup_personnel,
    verify_all_for_employer,
    verify_credentials,
)
from h1b_engine.credentials.reference import (
    normalize_institution_name,
    upsert_university,
)
from h1b_engine.db.base import get_session
from h1b_engine.db.models import (
    Beneficiary,
    CredentialClaim,
    UniversityProgram,
    UniversitySignatory,
)
from h1b_engine.utils.logging import setup_logging
from h1b_engine.utils.names import normalize_employer_name

app = typer.Typer(help="H-1B Personnel Look-Up / credential verification CLI")
console = Console()


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    setup_logging("DEBUG" if verbose else "INFO")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #


@app.command("bootstrap")
def bootstrap_cmd() -> None:
    """Seed the diploma-mill list + accredited credential evaluators."""
    result = bootstrap()
    console.print(
        f"[green]Bootstrap complete.[/green] "
        f"diploma_mills={result['diploma_mills']}, evaluators={result['evaluators']}"
    )


@app.command("add-university")
def add_university_cmd(
    name: str = typer.Option(..., "--name"),
    country: str = typer.Option("US", "--country"),
    status: str = typer.Option("ACCREDITED", "--status"),
    state: Optional[str] = typer.Option(None, "--state"),
    city: Optional[str] = typer.Option(None, "--city"),
    ipeds_id: Optional[str] = typer.Option(None, "--ipeds-id"),
    accreditor: Optional[str] = typer.Option(None, "--accreditor"),
    founded_year: Optional[int] = typer.Option(None, "--founded-year"),
    closed_year: Optional[int] = typer.Option(None, "--closed-year"),
    official_domain: Optional[str] = typer.Option(None, "--official-domain"),
    source_url: Optional[str] = typer.Option(None, "--source-url"),
) -> None:
    """Upsert a University row in the reference catalog."""
    with get_session() as session:
        uni = upsert_university(
            session,
            name=name,
            country=country,
            accreditation_status=status,
            state=state,
            city=city,
            ipeds_id=ipeds_id,
            accreditor=accreditor,
            founded_year=founded_year,
            closed_year=closed_year,
            official_domain=official_domain,
            source="MANUAL",
            source_url=source_url,
        )
        console.print(f"[green]Upserted[/green] university id={uni.id} {uni.name}")


@app.command("add-program")
def add_program_cmd(
    university_id: int = typer.Option(..., "--university-id"),
    degree_level: str = typer.Option(..., "--degree-level"),
    program_name: str = typer.Option(..., "--program-name"),
    cip_code: Optional[str] = typer.Option(None, "--cip-code"),
    first_conferred_year: Optional[int] = typer.Option(None, "--first-conferred-year"),
    last_conferred_year: Optional[int] = typer.Option(None, "--last-conferred-year"),
    source: str = typer.Option("MANUAL", "--source"),
    source_url: Optional[str] = typer.Option(None, "--source-url"),
) -> None:
    """Register a degree program at a university."""
    with get_session() as session:
        session.add(
            UniversityProgram(
                university_id=university_id,
                degree_level=degree_level.upper(),
                cip_code=cip_code,
                program_name=program_name,
                program_name_normalized=normalize_institution_name(program_name),
                first_conferred_year=first_conferred_year,
                last_conferred_year=last_conferred_year,
                source=source,
                source_url=source_url,
            )
        )
    console.print(f"[green]Added[/green] program '{program_name}' to university_id={university_id}")


@app.command("add-signatory")
def add_signatory_cmd(
    university_id: int = typer.Option(..., "--university-id"),
    full_name: str = typer.Option(..., "--full-name"),
    title: Optional[str] = typer.Option(None, "--title"),
    department: Optional[str] = typer.Option(None, "--department"),
    email: Optional[str] = typer.Option(None, "--email"),
    active_from: Optional[str] = typer.Option(None, "--active-from"),
    active_until: Optional[str] = typer.Option(None, "--active-until"),
    deceased: bool = typer.Option(False, "--deceased"),
    source: str = typer.Option("MANUAL", "--source"),
    source_url: Optional[str] = typer.Option(None, "--source-url"),
) -> None:
    """Register a transcript signatory / registrar / dean at a university."""
    with get_session() as session:
        session.add(
            UniversitySignatory(
                university_id=university_id,
                full_name=full_name,
                name_normalized=normalize_employer_name(full_name),
                title=title,
                department=department,
                email=email,
                active_from=_parse_date(active_from),
                active_until=_parse_date(active_until),
                is_deceased=1 if deceased else 0,
                source=source,
                source_url=source_url,
            )
        )
    console.print(
        f"[green]Added[/green] signatory '{full_name}' at university_id={university_id}"
    )


# --------------------------------------------------------------------------- #
# Beneficiary / claim intake
# --------------------------------------------------------------------------- #


@app.command("add-beneficiary")
def add_beneficiary_cmd(
    full_name: str = typer.Option(..., "--full-name"),
    source: str = typer.Option(..., "--source", help="USCIS_I129|FOIA|COURT|TIP|EMPLOYER_DISCLOSURE"),
    date_of_birth: Optional[str] = typer.Option(None, "--date-of-birth"),
    employer_id: Optional[int] = typer.Option(None, "--employer-id"),
    lca_case_number: Optional[str] = typer.Option(None, "--lca-case-number"),
    country_of_citizenship: Optional[str] = typer.Option(None, "--country-of-citizenship"),
    country_of_birth: Optional[str] = typer.Option(None, "--country-of-birth"),
    passport_last4: Optional[str] = typer.Option(None, "--passport-last4"),
    passport_country: Optional[str] = typer.Option(None, "--passport-country"),
    job_title_claimed: Optional[str] = typer.Option(None, "--job-title"),
    source_url: Optional[str] = typer.Option(None, "--source-url"),
) -> None:
    """Register a beneficiary record (must be sourced from public/FOIA/tip data)."""
    from sqlalchemy import select

    from h1b_engine.db.models import LcaFiling

    with get_session() as session:
        lca_id: int | None = None
        if lca_case_number:
            row = session.execute(
                select(LcaFiling.id).where(LcaFiling.case_number == lca_case_number)
            ).scalar_one_or_none()
            lca_id = row

        b = Beneficiary(
            employer_id=employer_id,
            lca_filing_id=lca_id,
            full_name=full_name,
            name_normalized=normalize_employer_name(full_name),
            date_of_birth=_parse_date(date_of_birth),
            country_of_birth=country_of_birth,
            country_of_citizenship=country_of_citizenship,
            passport_last4=passport_last4[-4:] if passport_last4 else None,
            passport_country=passport_country,
            job_title_claimed=job_title_claimed,
            source=source,
            source_url=source_url,
        )
        session.add(b)
        session.flush()
        console.print(f"[green]Added[/green] beneficiary id={b.id}")


@app.command("add-claim")
def add_claim_cmd(
    beneficiary_id: int = typer.Option(..., "--beneficiary-id"),
    claim_type: str = typer.Option("DEGREE", "--claim-type"),
    university_name: Optional[str] = typer.Option(None, "--university-name"),
    country: Optional[str] = typer.Option(None, "--country"),
    degree_level: Optional[str] = typer.Option(None, "--degree-level"),
    degree_title: Optional[str] = typer.Option(None, "--degree-title"),
    field_of_study: Optional[str] = typer.Option(None, "--field-of-study"),
    enrollment_start_date: Optional[str] = typer.Option(None, "--enrollment-start-date"),
    graduation_date: Optional[str] = typer.Option(None, "--graduation-date"),
    signatory_name: Optional[str] = typer.Option(None, "--signatory-name"),
    signatory_title: Optional[str] = typer.Option(None, "--signatory-title"),
    signatory_email: Optional[str] = typer.Option(None, "--signatory-email"),
    evaluator_name: Optional[str] = typer.Option(None, "--evaluator-name"),
    evaluator_organization: Optional[str] = typer.Option(None, "--evaluator-organization"),
    evidence_url: Optional[str] = typer.Option(None, "--evidence-url"),
) -> None:
    """Attach a credential claim to a beneficiary."""
    from h1b_engine.credentials.reference import resolve_university

    with get_session() as session:
        uni = resolve_university(session, university_name, country) if university_name else None
        claim = CredentialClaim(
            beneficiary_id=beneficiary_id,
            claim_type=claim_type.upper(),
            university_name_raw=university_name,
            university_id=uni.id if uni else None,
            country=country,
            degree_level=degree_level.upper() if degree_level else None,
            degree_title=degree_title,
            field_of_study=field_of_study,
            enrollment_start_date=_parse_date(enrollment_start_date),
            graduation_date=_parse_date(graduation_date),
            signatory_name_raw=signatory_name,
            signatory_title_raw=signatory_title,
            signatory_email_raw=signatory_email,
            evaluator_name_raw=evaluator_name,
            evaluator_organization_raw=evaluator_organization,
            evidence_url=evidence_url,
        )
        session.add(claim)
        session.flush()
        console.print(f"[green]Added[/green] credential claim id={claim.id}")


# --------------------------------------------------------------------------- #
# Verification / lookup
# --------------------------------------------------------------------------- #


def _render_report(report: PersonnelReport) -> None:
    console.print(
        f"\n[bold]Personnel report:[/bold] {report.full_name} "
        f"(beneficiary_id={report.beneficiary_id})"
    )
    console.print(
        f"  employer: {report.employer_name or '-'} "
        f"(id={report.employer_id or '-'}), "
        f"source={report.source}, dob={report.date_of_birth or '-'}"
    )
    console.print(
        f"  total credential score: {report.total_score:.0f} "
        f"({report.severity}) across {len(report.flags)} flag(s)"
    )

    if report.claims:
        tbl = Table(title="Claimed credentials", show_lines=False)
        tbl.add_column("ID")
        tbl.add_column("Type")
        tbl.add_column("University")
        tbl.add_column("Accredit.")
        tbl.add_column("Level")
        tbl.add_column("Field")
        tbl.add_column("Graduated")
        for c in report.claims:
            tbl.add_row(
                str(c.id),
                c.claim_type,
                (c.resolved_university_name or c.university_name_raw) or "-",
                c.accreditation_status or "-",
                c.degree_level or "-",
                (c.field_of_study or "-")[:30],
                c.graduation_date or "-",
            )
        console.print(tbl)

    if report.flags:
        tbl = Table(title="Verification flags", show_lines=False)
        tbl.add_column("Severity")
        tbl.add_column("Type")
        tbl.add_column("Score")
        tbl.add_column("Description")
        for f in report.flags:
            tbl.add_column
            tbl.add_row(f.severity, f.type, f"{f.score:.0f}", f.description)
        console.print(tbl)
    else:
        console.print("[green]No credential flags.[/green]")


@app.command("lookup")
def lookup_cmd(
    beneficiary_id: Optional[int] = typer.Option(None, "--beneficiary-id"),
    name: Optional[str] = typer.Option(None, "--name"),
    date_of_birth: Optional[str] = typer.Option(None, "--date-of-birth"),
    employer_id: Optional[int] = typer.Option(None, "--employer-id"),
    json_out: Optional[Path] = typer.Option(None, "--json-out"),
) -> None:
    """Verify credentials and print a personnel report.

    Provide one of --beneficiary-id, --name (with optional --date-of-birth),
    or --employer-id (batch mode).
    """
    reports: list[PersonnelReport] = []
    if beneficiary_id is not None:
        r = lookup_personnel(beneficiary_id)
        if r:
            reports.append(r)
    elif employer_id is not None:
        reports.extend(verify_all_for_employer(employer_id))
    elif name:
        reports.extend(lookup_by_name(name, _parse_date(date_of_birth)))
    else:
        console.print(
            "[red]Provide --beneficiary-id, --employer-id, or --name[/red]"
        )
        raise typer.Exit(1)

    if not reports:
        console.print("[yellow]No matching beneficiaries.[/yellow]")
        raise typer.Exit(0)

    for r in reports:
        _render_report(r)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps([r.to_dict() for r in reports], indent=2, default=str)
        )
        console.print(f"\n[green]Wrote[/green] {json_out}")


@app.command("verify")
def verify_cmd(
    beneficiary_id: int = typer.Option(..., "--beneficiary-id"),
) -> None:
    """Run the verification pipeline for a single beneficiary id."""
    flags = verify_credentials(beneficiary_id)
    if not flags:
        console.print("[green]No credential flags.[/green]")
        return
    for f in flags:
        console.print(f"[{f.severity}] {f.type} ({f.score:.0f} pts) — {f.description}")


if __name__ == "__main__":
    app()
