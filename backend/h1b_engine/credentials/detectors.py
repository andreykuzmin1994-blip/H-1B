"""Credential verification triggers.

Each detector takes a :class:`Beneficiary` + its associated
:class:`CredentialClaim` rows and returns zero or more
``(CredentialFlagDefinition, evidence, claim_id)`` tuples. The set of
detectors run by the verifier is deliberately conservative: we only emit a
flag when the reference data contains a positive counter-signal. Absence of
data about a signatory, for example, does NOT automatically fire
``SIGNATORY_NOT_AT_UNIVERSITY`` — we require that the institution itself has
signatory records loaded before calling the lookup a miss.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from h1b_engine.credentials.flags import (
    CREDENTIAL_FLAGS,
    FIELD_TO_SOC_MAJOR,
    MIN_DEGREE_YEARS,
    MIN_GRAD_AGE,
    CredentialFlagDefinition,
)
from h1b_engine.credentials.reference import (
    normalize_institution_name,
    resolve_university,
)
from h1b_engine.db.models import (
    Beneficiary,
    CredentialClaim,
    CredentialEvaluator,
    LcaFiling,
    University,
    UniversityProgram,
    UniversitySignatory,
    Violation,
)
from h1b_engine.utils.names import normalize_employer_name

DetectorOutput = tuple[CredentialFlagDefinition, dict[str, Any], int | None]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #


_EMAIL_DOMAIN_RE = re.compile(r"@([\w.\-]+)$")


def _email_domain(email: str | None) -> str | None:
    if not email:
        return None
    match = _EMAIL_DOMAIN_RE.search(email.strip().lower())
    return match.group(1) if match else None


def _age_years(dob: date | None, at: date | None) -> float | None:
    if not dob or not at:
        return None
    delta = at - dob
    return delta.days / 365.25


def _normalize_person_name(name: str | None) -> str:
    """Normalize a person's name for comparison. Reuses the employer helper."""
    return normalize_employer_name(name)


def _degree_level_norm(level: str | None) -> str:
    if not level:
        return ""
    raw = level.strip().upper()
    # Collapse common synonyms.
    if raw in {"BA", "BS", "BACHELORS", "BACHELOR'S", "UNDERGRADUATE"}:
        return "BACHELOR"
    if raw in {"MA", "MS", "MBA", "MASTERS", "MASTER'S"}:
        return "MASTER"
    if raw in {"PHD", "DOCTORATE", "DR", "DPHIL"}:
        return "DOCTORAL"
    if raw in {"AA", "AS"}:
        return "ASSOCIATE"
    if raw in {"JD", "MD", "DDS", "DVM", "PHARMD"}:
        return "PROFESSIONAL"
    return raw


# --------------------------------------------------------------------------- #
# Individual detectors
# --------------------------------------------------------------------------- #


def detect_university_status(
    session: Session,
    claim: CredentialClaim,
) -> list[DetectorOutput]:
    """University existence + accreditation + timeline sanity."""
    if claim.claim_type != "DEGREE":
        return []
    out: list[DetectorOutput] = []

    uni = (
        session.get(University, claim.university_id)
        if claim.university_id
        else resolve_university(session, claim.university_name_raw, claim.country)
    )
    if not uni:
        # No match anywhere in our reference data.
        if claim.university_name_raw:
            out.append(
                (
                    CREDENTIAL_FLAGS["UNIVERSITY_NOT_FOUND"],
                    {
                        "claimed_university": claim.university_name_raw,
                        "normalized": normalize_institution_name(
                            claim.university_name_raw
                        ),
                        "country": claim.country,
                    },
                    claim.id,
                )
            )
        return out

    status = (uni.accreditation_status or "UNKNOWN").upper()
    if status == "DIPLOMA_MILL":
        out.append(
            (
                CREDENTIAL_FLAGS["DIPLOMA_MILL_UNIVERSITY"],
                {
                    "university": uni.name,
                    "country": uni.country,
                    "source": uni.source,
                },
                claim.id,
            )
        )
    elif status in ("UNACCREDITED", "NOT_RECOGNIZED"):
        out.append(
            (
                CREDENTIAL_FLAGS["UNACCREDITED_UNIVERSITY"],
                {
                    "university": uni.name,
                    "country": uni.country,
                    "accreditation_status": status,
                },
                claim.id,
            )
        )

    grad = claim.graduation_date
    if grad:
        if uni.founded_year and grad.year < uni.founded_year:
            out.append(
                (
                    CREDENTIAL_FLAGS["UNIVERSITY_FOUNDED_AFTER_GRADUATION"],
                    {
                        "university": uni.name,
                        "founded_year": uni.founded_year,
                        "graduation_year": grad.year,
                    },
                    claim.id,
                )
            )
        if uni.closed_year and grad.year > uni.closed_year:
            out.append(
                (
                    CREDENTIAL_FLAGS["UNIVERSITY_CLOSED_BEFORE_GRADUATION"],
                    {
                        "university": uni.name,
                        "closed_year": uni.closed_year,
                        "graduation_year": grad.year,
                    },
                    claim.id,
                )
            )
    return out


def detect_degree_offered(
    session: Session,
    claim: CredentialClaim,
) -> list[DetectorOutput]:
    """Program offering + level + year-coverage."""
    if claim.claim_type != "DEGREE":
        return []
    uni_id = claim.university_id
    if uni_id is None:
        # Fall back to name-based resolution so callers who skip the resolver
        # still get useful detections.
        uni = resolve_university(session, claim.university_name_raw, claim.country)
        if uni is None:
            return []
        uni_id = uni.id
    out: list[DetectorOutput] = []
    level = _degree_level_norm(claim.degree_level)
    field_norm = normalize_institution_name(claim.field_of_study)

    programs = session.execute(
        select(UniversityProgram).where(UniversityProgram.university_id == uni_id)
    ).scalars().all()
    if not programs:
        # No program data loaded for this institution -> can't verify. Stay silent.
        return out

    level_match = [p for p in programs if _degree_level_norm(p.degree_level) == level]
    if level and not level_match:
        out.append(
            (
                CREDENTIAL_FLAGS["DEGREE_LEVEL_NOT_OFFERED"],
                {
                    "university_id": uni_id,
                    "claimed_level": level,
                    "available_levels": sorted(
                        {_degree_level_norm(p.degree_level) for p in programs}
                    ),
                },
                claim.id,
            )
        )
        return out  # No point checking fields when the level doesn't even exist.

    if field_norm and level_match:
        field_match = [
            p for p in level_match if _program_matches_field(p, field_norm)
        ]
        if not field_match:
            out.append(
                (
                    CREDENTIAL_FLAGS["DEGREE_NOT_OFFERED"],
                    {
                        "university_id": uni_id,
                        "claimed_field": claim.field_of_study,
                        "level": level,
                        "offered_programs": [p.program_name for p in level_match[:10]],
                    },
                    claim.id,
                )
            )
        else:
            grad = claim.graduation_date
            if grad:
                year = grad.year
                in_range = [
                    p
                    for p in field_match
                    if (
                        (p.first_conferred_year or year) <= year
                        <= (p.last_conferred_year or year)
                    )
                ]
                if not in_range:
                    out.append(
                        (
                            CREDENTIAL_FLAGS["DEGREE_NOT_OFFERED_IN_YEAR"],
                            {
                                "university_id": uni_id,
                                "claimed_year": year,
                                "program_windows": [
                                    {
                                        "program": p.program_name,
                                        "first_conferred_year": p.first_conferred_year,
                                        "last_conferred_year": p.last_conferred_year,
                                    }
                                    for p in field_match[:5]
                                ],
                            },
                            claim.id,
                        )
                    )
    return out


def _program_matches_field(program: UniversityProgram, field_norm: str) -> bool:
    """Token-overlap match between a program name and a claimed field."""
    if not field_norm:
        return False
    prog_norm = program.program_name_normalized or normalize_institution_name(
        program.program_name
    )
    if not prog_norm:
        return False
    prog_tokens = {t for t in prog_norm.split() if len(t) > 2}
    field_tokens = {t for t in field_norm.split() if len(t) > 2}
    return bool(prog_tokens & field_tokens)


def detect_signatory(
    session: Session, claim: CredentialClaim
) -> list[DetectorOutput]:
    """Signatory presence + activity window + email domain + death-date."""
    if claim.claim_type != "DEGREE" or not claim.signatory_name_raw:
        return []
    uni_id = claim.university_id
    uni = session.get(University, uni_id) if uni_id else None
    if uni is None:
        uni = resolve_university(session, claim.university_name_raw, claim.country)
        uni_id = uni.id if uni else None
    if uni_id is None:
        return []
    out: list[DetectorOutput] = []

    norm = _normalize_person_name(claim.signatory_name_raw)
    sigs = session.execute(
        select(UniversitySignatory).where(
            UniversitySignatory.university_id == uni_id
        )
    ).scalars().all()

    # If the institution has no loaded signatory data, stay silent.
    if not sigs:
        return out

    matches = [s for s in sigs if s.name_normalized == norm]
    grad = claim.graduation_date

    if not matches:
        out.append(
            (
                CREDENTIAL_FLAGS["SIGNATORY_NOT_AT_UNIVERSITY"],
                {
                    "claimed_signatory": claim.signatory_name_raw,
                    "claimed_title": claim.signatory_title_raw,
                    "university": uni.name if uni else None,
                    "known_signatory_count": len(sigs),
                },
                claim.id,
            )
        )
        return out

    if grad:
        active_hits: list[UniversitySignatory] = []
        dead_at_sign: list[UniversitySignatory] = []
        for s in matches:
            if s.is_deceased and s.active_until and grad > s.active_until:
                dead_at_sign.append(s)
                continue
            if (s.active_from and grad < s.active_from) or (
                s.active_until and grad > s.active_until
            ):
                continue
            active_hits.append(s)
        if dead_at_sign:
            s = dead_at_sign[0]
            out.append(
                (
                    CREDENTIAL_FLAGS["SIGNATORY_DECEASED_AT_SIGN_DATE"],
                    {
                        "signatory": claim.signatory_name_raw,
                        "death_on_or_before": (
                            s.active_until.isoformat() if s.active_until else None
                        ),
                        "claimed_signing_date": grad.isoformat(),
                    },
                    claim.id,
                )
            )
        elif not active_hits:
            s = matches[0]
            out.append(
                (
                    CREDENTIAL_FLAGS["SIGNATORY_INACTIVE_AT_SIGN_DATE"],
                    {
                        "signatory": claim.signatory_name_raw,
                        "active_from": (
                            s.active_from.isoformat() if s.active_from else None
                        ),
                        "active_until": (
                            s.active_until.isoformat() if s.active_until else None
                        ),
                        "claimed_signing_date": grad.isoformat(),
                    },
                    claim.id,
                )
            )

    # Email-domain mismatch check fires regardless of the activity window.
    email_domain = _email_domain(claim.signatory_email_raw)
    if email_domain and uni and uni.official_domain:
        official = uni.official_domain.strip().lower().lstrip("@")
        # Accept exact or subdomain match (e.g. grad.stanford.edu of stanford.edu).
        if not (email_domain == official or email_domain.endswith("." + official)):
            out.append(
                (
                    CREDENTIAL_FLAGS["SIGNATORY_EMAIL_DOMAIN_MISMATCH"],
                    {
                        "claimed_email_domain": email_domain,
                        "official_domain": official,
                    },
                    claim.id,
                )
            )
    return out


def detect_timeline(
    beneficiary: Beneficiary, claim: CredentialClaim
) -> list[DetectorOutput]:
    """Birth-date / graduation timeline sanity."""
    if claim.claim_type != "DEGREE":
        return []
    out: list[DetectorOutput] = []
    grad = claim.graduation_date
    start = claim.enrollment_start_date
    today = date.today()
    if grad:
        if grad > today + timedelta(days=180):
            # Allow up to six months future-dated (degree-in-progress attestations),
            # beyond that it is implausible.
            out.append(
                (
                    CREDENTIAL_FLAGS["IMPOSSIBLE_GRADUATION_DATE"],
                    {"graduation_date": grad.isoformat(), "reason": "future_dated"},
                    claim.id,
                )
            )
        if beneficiary.date_of_birth and grad < beneficiary.date_of_birth:
            out.append(
                (
                    CREDENTIAL_FLAGS["IMPOSSIBLE_GRADUATION_DATE"],
                    {
                        "graduation_date": grad.isoformat(),
                        "date_of_birth": beneficiary.date_of_birth.isoformat(),
                        "reason": "before_birth",
                    },
                    claim.id,
                )
            )
        if beneficiary.date_of_birth:
            age = _age_years(beneficiary.date_of_birth, grad)
            level = _degree_level_norm(claim.degree_level)
            minimum = MIN_GRAD_AGE.get(level)
            if age is not None and minimum is not None and age < minimum:
                out.append(
                    (
                        CREDENTIAL_FLAGS["UNDERAGE_DEGREE"],
                        {
                            "age_at_graduation": round(age, 1),
                            "minimum_expected": minimum,
                            "degree_level": level,
                        },
                        claim.id,
                    )
                )
    if grad and start:
        if start > grad:
            out.append(
                (
                    CREDENTIAL_FLAGS["ENROLLMENT_AFTER_GRADUATION"],
                    {
                        "enrollment_start_date": start.isoformat(),
                        "graduation_date": grad.isoformat(),
                    },
                    claim.id,
                )
            )
        else:
            years = (grad - start).days / 365.25
            level = _degree_level_norm(claim.degree_level)
            minimum_years = MIN_DEGREE_YEARS.get(level)
            if minimum_years is not None and years < minimum_years:
                out.append(
                    (
                        CREDENTIAL_FLAGS["DEGREE_DURATION_IMPLAUSIBLE"],
                        {
                            "years_elapsed": round(years, 2),
                            "minimum_expected_years": minimum_years,
                            "degree_level": level,
                        },
                        claim.id,
                    )
                )
    return out


def detect_evaluator(
    session: Session, claim: CredentialClaim
) -> list[DetectorOutput]:
    """Foreign-credential evaluator membership check."""
    if claim.claim_type != "EVALUATION":
        return []
    org = claim.evaluator_organization_raw or claim.evaluator_name_raw
    if not org:
        return []
    norm = normalize_institution_name(org)
    evaluator = session.execute(
        select(CredentialEvaluator).where(
            CredentialEvaluator.name_normalized == norm
        )
    ).scalar_one_or_none()
    if evaluator is None:
        return [
            (
                CREDENTIAL_FLAGS["EVALUATOR_UNKNOWN"],
                {"evaluator_raw": org, "normalized": norm},
                claim.id,
            )
        ]
    if not (evaluator.naces_member or evaluator.aice_member):
        return [
            (
                CREDENTIAL_FLAGS["EVALUATOR_NOT_ACCREDITED"],
                {
                    "evaluator": evaluator.name,
                    "naces_member": bool(evaluator.naces_member),
                    "aice_member": bool(evaluator.aice_member),
                },
                claim.id,
            )
        ]
    return []


def detect_degree_soc_mismatch(
    session: Session,
    beneficiary: Beneficiary,
    claims: Iterable[CredentialClaim],
) -> list[DetectorOutput]:
    """Specialty-occupation nexus: claimed field of study must plausibly map to SOC."""
    out: list[DetectorOutput] = []
    if not beneficiary.lca_filing_id:
        return out
    filing = session.get(LcaFiling, beneficiary.lca_filing_id)
    if not filing or not filing.soc_code:
        return out
    soc_major = (
        filing.soc_code.split("-")[0]
        if "-" in filing.soc_code
        else filing.soc_code[:2]
    )
    any_match = False
    fields_seen: list[str] = []
    for claim in claims:
        if claim.claim_type != "DEGREE" or not claim.field_of_study:
            continue
        fields_seen.append(claim.field_of_study)
        field_norm = claim.field_of_study.strip().lower()
        for keyword, soc_majors in FIELD_TO_SOC_MAJOR.items():
            if keyword in field_norm:
                if soc_major in soc_majors:
                    any_match = True
                    break
    if fields_seen and not any_match:
        out.append(
            (
                CREDENTIAL_FLAGS["DEGREE_FIELD_SOC_MISMATCH"],
                {
                    "soc_code": filing.soc_code,
                    "soc_major": soc_major,
                    "fields_of_study": fields_seen,
                },
                None,
            )
        )
    return out


def detect_identity_reuse(
    session: Session, beneficiary: Beneficiary
) -> list[DetectorOutput]:
    """Duplicate name+DOB or passport across beneficiaries at unrelated employers."""
    out: list[DetectorOutput] = []
    # Same normalized name + DOB across multiple employers.
    if beneficiary.date_of_birth and beneficiary.name_normalized:
        rows = session.execute(
            select(Beneficiary).where(
                Beneficiary.name_normalized == beneficiary.name_normalized,
                Beneficiary.date_of_birth == beneficiary.date_of_birth,
                Beneficiary.id != beneficiary.id,
            )
        ).scalars().all()
        other_employers = {
            r.employer_id for r in rows if r.employer_id and r.employer_id != beneficiary.employer_id
        }
        if other_employers:
            out.append(
                (
                    CREDENTIAL_FLAGS["DUPLICATE_BENEFICIARY_IDENTITY"],
                    {
                        "shared_with_employer_ids": sorted(other_employers),
                        "name_normalized": beneficiary.name_normalized,
                    },
                    None,
                )
            )

    # Same passport last4 + country across distinct names.
    if beneficiary.passport_last4 and beneficiary.passport_country:
        rows = session.execute(
            select(Beneficiary).where(
                Beneficiary.passport_last4 == beneficiary.passport_last4,
                Beneficiary.passport_country == beneficiary.passport_country,
                Beneficiary.id != beneficiary.id,
            )
        ).scalars().all()
        other_names = {
            r.name_normalized for r in rows if r.name_normalized != beneficiary.name_normalized
        }
        if other_names:
            out.append(
                (
                    CREDENTIAL_FLAGS["PASSPORT_NUMBER_REUSE"],
                    {
                        "passport_country": beneficiary.passport_country,
                        "passport_last4": beneficiary.passport_last4,
                        "distinct_names_observed": len(other_names) + 1,
                    },
                    None,
                )
            )
    return out


def detect_debarred_employer(
    session: Session, beneficiary: Beneficiary
) -> list[DetectorOutput]:
    """Beneficiary previously sponsored by a debarred / willful-violator employer."""
    if not beneficiary.name_normalized or not beneficiary.date_of_birth:
        return []
    rows = session.execute(
        select(Beneficiary.employer_id).where(
            Beneficiary.name_normalized == beneficiary.name_normalized,
            Beneficiary.date_of_birth == beneficiary.date_of_birth,
        )
    ).all()
    employer_ids = {r[0] for r in rows if r[0] is not None}
    if not employer_ids:
        return []
    violator_rows = session.execute(
        select(Violation.employer_id).where(Violation.employer_id.in_(employer_ids))
    ).all()
    violator_ids = {r[0] for r in violator_rows if r[0] is not None}
    if not violator_ids:
        return []
    return [
        (
            CREDENTIAL_FLAGS["BENEFICIARY_ON_DEBARRED_EMPLOYER"],
            {"debarred_employer_ids": sorted(violator_ids)},
            None,
        )
    ]


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #


def detect_for_beneficiary(
    session: Session, beneficiary: Beneficiary
) -> list[DetectorOutput]:
    """Run the full detector suite for one beneficiary."""
    claims = session.execute(
        select(CredentialClaim).where(CredentialClaim.beneficiary_id == beneficiary.id)
    ).scalars().all()

    outputs: list[DetectorOutput] = []
    for claim in claims:
        outputs.extend(detect_university_status(session, claim))
        outputs.extend(detect_degree_offered(session, claim))
        outputs.extend(detect_signatory(session, claim))
        outputs.extend(detect_timeline(beneficiary, claim))
        outputs.extend(detect_evaluator(session, claim))
    outputs.extend(detect_degree_soc_mismatch(session, beneficiary, claims))
    outputs.extend(detect_identity_reuse(session, beneficiary))
    outputs.extend(detect_debarred_employer(session, beneficiary))
    return _dedupe(outputs)


def _dedupe(outputs: list[DetectorOutput]) -> list[DetectorOutput]:
    """Keep only the first (highest-severity) occurrence of each flag_type/claim_id."""
    seen: set[tuple[str, int | None]] = set()
    deduped: list[DetectorOutput] = []
    for flag, evidence, claim_id in outputs:
        key = (flag.type, claim_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((flag, evidence, claim_id))
    return deduped
