"""Personnel Look-Up Tool — public API.

Three entry points:

* :func:`lookup_personnel` — verify one beneficiary by id and return a
  structured :class:`PersonnelReport`.
* :func:`lookup_by_name` — find beneficiaries by (optionally) name + DOB.
* :func:`verify_all_for_employer` — batch-verify every beneficiary linked to
  an employer. Used by the investigation connector.

All three persist :class:`CredentialFlag` rows transactionally. Calls are
idempotent: existing flag rows for a beneficiary are cleared before the
detector suite runs again.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from h1b_engine.credentials.detectors import (
    DetectorOutput,
    detect_for_beneficiary,
)
from h1b_engine.credentials.reference import (
    bootstrap_reference_data,
    resolve_university,
)
from h1b_engine.db.base import get_session
from h1b_engine.db.models import (
    Beneficiary,
    CredentialClaim,
    CredentialFlag,
    Employer,
    University,
)
from h1b_engine.utils.names import normalize_employer_name

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Report dataclasses
# --------------------------------------------------------------------------- #


@dataclass
class FlagRecord:
    type: str
    severity: str
    score: float
    description: str
    evidence: dict[str, Any]
    credential_claim_id: int | None = None


@dataclass
class ClaimRecord:
    id: int
    claim_type: str
    university_name_raw: str | None
    university_id: int | None
    resolved_university_name: str | None
    accreditation_status: str | None
    degree_level: str | None
    degree_title: str | None
    field_of_study: str | None
    country: str | None
    enrollment_start_date: str | None
    graduation_date: str | None
    signatory_name_raw: str | None
    signatory_title_raw: str | None
    signatory_email_raw: str | None
    evaluator_name_raw: str | None
    evaluator_organization_raw: str | None
    evidence_url: str | None


@dataclass
class PersonnelReport:
    beneficiary_id: int
    employer_id: int | None
    employer_name: str | None
    full_name: str
    date_of_birth: str | None
    country_of_citizenship: str | None
    source: str
    claims: list[ClaimRecord] = field(default_factory=list)
    flags: list[FlagRecord] = field(default_factory=list)

    @property
    def total_score(self) -> float:
        return sum(f.score for f in self.flags)

    @property
    def severity(self) -> str:
        score = self.total_score
        if score >= 75:
            return "CRITICAL"
        if score >= 50:
            return "HIGH"
        if score >= 25:
            return "MEDIUM"
        return "LOW"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["total_score"] = self.total_score
        d["severity"] = self.severity
        return d


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


def _persist_flags(
    session: Session,
    beneficiary: Beneficiary,
    outputs: list[DetectorOutput],
) -> list[FlagRecord]:
    """Replace existing credential flags with the detector output."""
    session.query(CredentialFlag).filter(
        CredentialFlag.beneficiary_id == beneficiary.id
    ).delete()
    records: list[FlagRecord] = []
    for flag, evidence, claim_id in outputs:
        session.add(
            CredentialFlag(
                beneficiary_id=beneficiary.id,
                credential_claim_id=claim_id,
                employer_id=beneficiary.employer_id,
                flag_type=flag.type,
                flag_severity=flag.severity,
                flag_score=flag.score,
                description=flag.description,
                evidence=evidence,
            )
        )
        records.append(
            FlagRecord(
                type=flag.type,
                severity=flag.severity,
                score=float(flag.score),
                description=flag.description,
                evidence=evidence,
                credential_claim_id=claim_id,
            )
        )
    return records


def _claim_records(session: Session, claims: list[CredentialClaim]) -> list[ClaimRecord]:
    out: list[ClaimRecord] = []
    for c in claims:
        uni = (
            session.get(University, c.university_id) if c.university_id else None
        )
        if uni is None and c.university_name_raw:
            uni = resolve_university(session, c.university_name_raw, c.country)
        out.append(
            ClaimRecord(
                id=c.id,
                claim_type=c.claim_type,
                university_name_raw=c.university_name_raw,
                university_id=uni.id if uni else None,
                resolved_university_name=uni.name if uni else None,
                accreditation_status=uni.accreditation_status if uni else None,
                degree_level=c.degree_level,
                degree_title=c.degree_title,
                field_of_study=c.field_of_study,
                country=c.country,
                enrollment_start_date=(
                    c.enrollment_start_date.isoformat()
                    if c.enrollment_start_date
                    else None
                ),
                graduation_date=(
                    c.graduation_date.isoformat() if c.graduation_date else None
                ),
                signatory_name_raw=c.signatory_name_raw,
                signatory_title_raw=c.signatory_title_raw,
                signatory_email_raw=c.signatory_email_raw,
                evaluator_name_raw=c.evaluator_name_raw,
                evaluator_organization_raw=c.evaluator_organization_raw,
                evidence_url=c.evidence_url,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #


def verify_credentials(
    beneficiary_id: int,
    session: Session | None = None,
) -> list[FlagRecord]:
    """Run all detectors for a single beneficiary and persist results."""
    if session is not None:
        return _verify(session, beneficiary_id)
    with get_session() as session:
        return _verify(session, beneficiary_id)


def _verify(session: Session, beneficiary_id: int) -> list[FlagRecord]:
    beneficiary = session.get(Beneficiary, beneficiary_id)
    if not beneficiary:
        return []
    outputs = detect_for_beneficiary(session, beneficiary)
    return _persist_flags(session, beneficiary, outputs)


def lookup_personnel(
    beneficiary_id: int,
    session: Session | None = None,
) -> PersonnelReport | None:
    """Verify a beneficiary and return a :class:`PersonnelReport`."""
    if session is None:
        with get_session() as session:
            return _lookup(session, beneficiary_id)
    return _lookup(session, beneficiary_id)


def _lookup(session: Session, beneficiary_id: int) -> PersonnelReport | None:
    beneficiary = session.get(Beneficiary, beneficiary_id)
    if not beneficiary:
        return None
    employer = (
        session.get(Employer, beneficiary.employer_id)
        if beneficiary.employer_id
        else None
    )
    claims = session.execute(
        select(CredentialClaim).where(
            CredentialClaim.beneficiary_id == beneficiary_id
        )
    ).scalars().all()
    outputs = detect_for_beneficiary(session, beneficiary)
    flags = _persist_flags(session, beneficiary, outputs)

    return PersonnelReport(
        beneficiary_id=beneficiary.id,
        employer_id=beneficiary.employer_id,
        employer_name=employer.name if employer else None,
        full_name=beneficiary.full_name,
        date_of_birth=(
            beneficiary.date_of_birth.isoformat()
            if beneficiary.date_of_birth
            else None
        ),
        country_of_citizenship=beneficiary.country_of_citizenship,
        source=beneficiary.source,
        claims=_claim_records(session, claims),
        flags=flags,
    )


def lookup_by_name(
    name: str,
    date_of_birth: date | None = None,
    session: Session | None = None,
) -> list[PersonnelReport]:
    """Locate beneficiary records matching a normalized name (+ optional DOB)."""
    if session is None:
        with get_session() as session:
            return _lookup_by_name(session, name, date_of_birth)
    return _lookup_by_name(session, name, date_of_birth)


def _lookup_by_name(
    session: Session, name: str, dob: date | None
) -> list[PersonnelReport]:
    norm = normalize_employer_name(name)
    stmt = select(Beneficiary).where(Beneficiary.name_normalized == norm)
    if dob:
        stmt = stmt.where(Beneficiary.date_of_birth == dob)
    ids = [row.id for row in session.execute(stmt).scalars().all()]
    return [r for bid in ids if (r := _lookup(session, bid)) is not None]


def verify_all_for_employer(
    employer_id: int,
    session: Session | None = None,
) -> list[PersonnelReport]:
    """Batch-verify every beneficiary linked to an employer."""
    if session is None:
        with get_session() as session:
            return _verify_all_for_employer(session, employer_id)
    return _verify_all_for_employer(session, employer_id)


def _verify_all_for_employer(
    session: Session, employer_id: int
) -> list[PersonnelReport]:
    ids = [
        row[0]
        for row in session.execute(
            select(Beneficiary.id).where(Beneficiary.employer_id == employer_id)
        ).all()
    ]
    reports: list[PersonnelReport] = []
    for bid in ids:
        report = _lookup(session, bid)
        if report is not None:
            reports.append(report)
    return reports


# --------------------------------------------------------------------------- #
# Bootstrapping
# --------------------------------------------------------------------------- #


def bootstrap(session: Session | None = None) -> dict[str, int]:
    """Seed the reference data tables (diploma-mill list, accredited evaluators)."""
    if session is None:
        with get_session() as session:
            return bootstrap_reference_data(session)
    return bootstrap_reference_data(session)
