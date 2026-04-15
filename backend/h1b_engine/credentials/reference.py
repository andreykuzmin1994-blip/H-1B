"""Reference-data loaders for the personnel lookup tool.

The detectors query three reference tables — ``universities``,
``university_programs``, ``university_signatories`` — and one aux table for
credential evaluators. Production deployments should ingest:

* IPEDS directory (US institutions, programs by CIP)
* ENIC-NARIC / Anabin / WES country listings (foreign institutions)
* GAO + Oregon ODA diploma-mill lists
* NACES + AICE evaluator membership pages
* University registrar / faculty directories (per-institution scrape)

The helpers below seed a minimal reference set so the verifier works out of
the box and tests have something to hit. Callers can replace / supplement the
seeded data via ``ingest_*`` helpers.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from h1b_engine.credentials.flags import (
    KNOWN_CRED_EVALUATORS,
    KNOWN_DIPLOMA_MILLS,
)
from h1b_engine.db.models import CredentialEvaluator, University
from h1b_engine.utils.names import normalize_employer_name


def normalize_institution_name(name: str | None) -> str:
    """Normalize a university name for cross-source matching.

    Reuses the employer-name normalizer — strips punctuation, common suffixes
    (``UNIVERSITY``-like tokens stay intact), and collapses whitespace.
    """
    return normalize_employer_name(name)


def seed_diploma_mills(session: Session) -> int:
    """Insert the static diploma-mill list if not already present."""
    inserted = 0
    for name, country in KNOWN_DIPLOMA_MILLS:
        norm = normalize_institution_name(name)
        existing = session.execute(
            select(University).where(
                University.name_normalized == norm,
                University.country == country,
            )
        ).scalar_one_or_none()
        if existing:
            if existing.accreditation_status != "DIPLOMA_MILL":
                existing.accreditation_status = "DIPLOMA_MILL"
            continue
        session.add(
            University(
                name=name,
                name_normalized=norm,
                country=country,
                accreditation_status="DIPLOMA_MILL",
                source="SEED_DIPLOMA_MILL",
            )
        )
        inserted += 1
    return inserted


def seed_credential_evaluators(session: Session) -> int:
    inserted = 0
    for rec in KNOWN_CRED_EVALUATORS:
        norm = normalize_institution_name(rec["name"])
        existing = session.execute(
            select(CredentialEvaluator).where(
                CredentialEvaluator.name_normalized == norm
            )
        ).scalar_one_or_none()
        if existing:
            # Keep flags fresh.
            existing.naces_member = 1 if rec.get("naces") else existing.naces_member
            existing.aice_member = 1 if rec.get("aice") else existing.aice_member
            continue
        session.add(
            CredentialEvaluator(
                name=rec["name"],
                name_normalized=norm,
                naces_member=1 if rec.get("naces") else 0,
                aice_member=1 if rec.get("aice") else 0,
                source="SEED_NACES_AICE",
            )
        )
        inserted += 1
    return inserted


def upsert_university(
    session: Session,
    *,
    name: str,
    country: str,
    accreditation_status: str = "ACCREDITED",
    state: str | None = None,
    city: str | None = None,
    ipeds_id: str | None = None,
    opeid: str | None = None,
    accreditor: str | None = None,
    founded_year: int | None = None,
    closed_year: int | None = None,
    official_domain: str | None = None,
    source: str = "MANUAL",
    source_url: str | None = None,
) -> University:
    norm = normalize_institution_name(name)
    existing = session.execute(
        select(University).where(
            University.name_normalized == norm,
            University.country == country,
        )
    ).scalar_one_or_none()
    if existing:
        # Only overwrite fields when caller provides a non-None value.
        for attr, value in {
            "state": state,
            "city": city,
            "ipeds_id": ipeds_id,
            "opeid": opeid,
            "accreditor": accreditor,
            "founded_year": founded_year,
            "closed_year": closed_year,
            "official_domain": official_domain,
            "source_url": source_url,
        }.items():
            if value is not None:
                setattr(existing, attr, value)
        # Only upgrade accreditation from UNKNOWN; never downgrade DIPLOMA_MILL.
        if (
            existing.accreditation_status in ("UNKNOWN", None)
            and accreditation_status
        ):
            existing.accreditation_status = accreditation_status
        return existing
    uni = University(
        name=name,
        name_normalized=norm,
        country=country,
        state=state,
        city=city,
        ipeds_id=ipeds_id,
        opeid=opeid,
        accreditor=accreditor,
        accreditation_status=accreditation_status,
        founded_year=founded_year,
        closed_year=closed_year,
        official_domain=official_domain,
        source=source,
        source_url=source_url,
    )
    session.add(uni)
    session.flush()
    return uni


def bootstrap_reference_data(session: Session) -> dict[str, int]:
    """Seed the minimum reference data the verifier needs to operate."""
    return {
        "diploma_mills": seed_diploma_mills(session),
        "evaluators": seed_credential_evaluators(session),
    }


def resolve_university(
    session: Session, name: str | None, country: str | None = None
) -> University | None:
    """Return a University row matching the provided name (+ optional country)."""
    if not name:
        return None
    norm = normalize_institution_name(name)
    stmt = select(University).where(University.name_normalized == norm)
    if country:
        stmt = stmt.where(University.country == country)
    rows = session.execute(stmt).scalars().all()
    if not rows:
        return None
    if len(rows) == 1 or country:
        return rows[0]
    # Prefer US row when country not specified (H-1B filings more often claim US).
    for row in rows:
        if row.country == "US":
            return row
    return rows[0]
