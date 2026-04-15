"""Credential verification flag definitions.

Each flag is raised by a corresponding detector in
:mod:`h1b_engine.credentials.detectors`. Severity and score follow the same
CRITICAL/HIGH/MEDIUM/LOW ladder used by the employer-level scoring engine so
the two subsystems can be blended into a single investigation report.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CredentialFlagDefinition:
    type: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    score: float
    description: str


CREDENTIAL_FLAGS: dict[str, CredentialFlagDefinition] = {
    # --- University existence / accreditation ---------------------------- #
    "UNIVERSITY_NOT_FOUND": CredentialFlagDefinition(
        type="UNIVERSITY_NOT_FOUND",
        severity="CRITICAL",
        score=40,
        description=(
            "Claimed issuing institution does not exist in IPEDS / ENIC-NARIC / "
            "national accreditation registries"
        ),
    ),
    "DIPLOMA_MILL_UNIVERSITY": CredentialFlagDefinition(
        type="DIPLOMA_MILL_UNIVERSITY",
        severity="CRITICAL",
        score=45,
        description=(
            "Institution appears on a published diploma-mill list (GAO, Oregon "
            "ODA, state AG enforcement, CHEA non-recognition)"
        ),
    ),
    "UNACCREDITED_UNIVERSITY": CredentialFlagDefinition(
        type="UNACCREDITED_UNIVERSITY",
        severity="HIGH",
        score=25,
        description=(
            "Institution exists but is not accredited by a USDE / CHEA / "
            "recognized foreign accreditor"
        ),
    ),
    "UNIVERSITY_CLOSED_BEFORE_GRADUATION": CredentialFlagDefinition(
        type="UNIVERSITY_CLOSED_BEFORE_GRADUATION",
        severity="CRITICAL",
        score=40,
        description=(
            "Institution had permanently closed before the claimed graduation date"
        ),
    ),
    "UNIVERSITY_FOUNDED_AFTER_GRADUATION": CredentialFlagDefinition(
        type="UNIVERSITY_FOUNDED_AFTER_GRADUATION",
        severity="CRITICAL",
        score=40,
        description=(
            "Institution was founded after the claimed graduation date"
        ),
    ),

    # --- Degree / program offering --------------------------------------- #
    "DEGREE_NOT_OFFERED": CredentialFlagDefinition(
        type="DEGREE_NOT_OFFERED",
        severity="HIGH",
        score=30,
        description=(
            "No record that the claimed degree program is (or was) offered at "
            "the issuing institution"
        ),
    ),
    "DEGREE_LEVEL_NOT_OFFERED": CredentialFlagDefinition(
        type="DEGREE_LEVEL_NOT_OFFERED",
        severity="HIGH",
        score=25,
        description=(
            "Institution does not confer the claimed degree level (e.g. no "
            "doctoral programs, community-college claim of bachelor's degree)"
        ),
    ),
    "DEGREE_NOT_OFFERED_IN_YEAR": CredentialFlagDefinition(
        type="DEGREE_NOT_OFFERED_IN_YEAR",
        severity="HIGH",
        score=25,
        description=(
            "Claimed graduation year falls outside the program's first/last "
            "conferred years"
        ),
    ),

    # --- Signatory authenticity ------------------------------------------ #
    "SIGNATORY_NOT_AT_UNIVERSITY": CredentialFlagDefinition(
        type="SIGNATORY_NOT_AT_UNIVERSITY",
        severity="CRITICAL",
        score=35,
        description=(
            "Person who signed the transcript / degree is not on the "
            "institution's faculty or registrar directory"
        ),
    ),
    "SIGNATORY_INACTIVE_AT_SIGN_DATE": CredentialFlagDefinition(
        type="SIGNATORY_INACTIVE_AT_SIGN_DATE",
        severity="HIGH",
        score=30,
        description=(
            "Signatory worked at the institution but not during the claimed "
            "signing window (left, retired, or not yet hired)"
        ),
    ),
    "SIGNATORY_DECEASED_AT_SIGN_DATE": CredentialFlagDefinition(
        type="SIGNATORY_DECEASED_AT_SIGN_DATE",
        severity="CRITICAL",
        score=45,
        description="Named signatory was deceased on or before the claimed signing date",
    ),
    "SIGNATORY_EMAIL_DOMAIN_MISMATCH": CredentialFlagDefinition(
        type="SIGNATORY_EMAIL_DOMAIN_MISMATCH",
        severity="MEDIUM",
        score=15,
        description=(
            "Signatory contact email does not use the institution's official "
            "domain (possible gmail/hotmail impersonation)"
        ),
    ),

    # --- Timeline plausibility ------------------------------------------- #
    "IMPOSSIBLE_GRADUATION_DATE": CredentialFlagDefinition(
        type="IMPOSSIBLE_GRADUATION_DATE",
        severity="CRITICAL",
        score=40,
        description=(
            "Graduation date is in the future or precedes the beneficiary's "
            "date of birth"
        ),
    ),
    "UNDERAGE_DEGREE": CredentialFlagDefinition(
        type="UNDERAGE_DEGREE",
        severity="HIGH",
        score=25,
        description=(
            "Beneficiary's age at claimed graduation is below the plausible "
            "minimum for the degree level (bachelor<17, master<19, doctoral<22)"
        ),
    ),
    "ENROLLMENT_AFTER_GRADUATION": CredentialFlagDefinition(
        type="ENROLLMENT_AFTER_GRADUATION",
        severity="HIGH",
        score=25,
        description="Claimed enrollment start date is after the graduation date",
    ),
    "DEGREE_DURATION_IMPLAUSIBLE": CredentialFlagDefinition(
        type="DEGREE_DURATION_IMPLAUSIBLE",
        severity="MEDIUM",
        score=15,
        description=(
            "Time between enrollment and graduation is implausibly short for "
            "the degree level (e.g. bachelor's <2 years, doctoral <2 years)"
        ),
    ),

    # --- Identity reuse -------------------------------------------------- #
    "DUPLICATE_BENEFICIARY_IDENTITY": CredentialFlagDefinition(
        type="DUPLICATE_BENEFICIARY_IDENTITY",
        severity="HIGH",
        score=25,
        description=(
            "Same name + date of birth appears on filings for two or more "
            "unrelated employers (possible identity-sharing scheme)"
        ),
    ),
    "PASSPORT_NUMBER_REUSE": CredentialFlagDefinition(
        type="PASSPORT_NUMBER_REUSE",
        severity="CRITICAL",
        score=40,
        description=(
            "Same passport country + last-4 associated with multiple distinct "
            "beneficiary names"
        ),
    ),
    "BENEFICIARY_ON_DEBARRED_EMPLOYER": CredentialFlagDefinition(
        type="BENEFICIARY_ON_DEBARRED_EMPLOYER",
        severity="HIGH",
        score=25,
        description=(
            "Beneficiary was previously sponsored by an employer later debarred "
            "under INA section 212(n) or found a willful violator"
        ),
    ),

    # --- Evaluation authenticity ----------------------------------------- #
    "EVALUATOR_NOT_ACCREDITED": CredentialFlagDefinition(
        type="EVALUATOR_NOT_ACCREDITED",
        severity="HIGH",
        score=25,
        description=(
            "Foreign credential evaluator is not a NACES or AICE member "
            "(unreliable for specialty occupation adjudication)"
        ),
    ),
    "EVALUATOR_UNKNOWN": CredentialFlagDefinition(
        type="EVALUATOR_UNKNOWN",
        severity="MEDIUM",
        score=12,
        description=(
            "Foreign credential evaluator could not be located in any "
            "professional association registry"
        ),
    ),

    # --- Degree / occupation mismatch ------------------------------------ #
    "DEGREE_FIELD_SOC_MISMATCH": CredentialFlagDefinition(
        type="DEGREE_FIELD_SOC_MISMATCH",
        severity="MEDIUM",
        score=18,
        description=(
            "Claimed field of study has no recognized nexus with the SOC "
            "occupation (specialty-occupation requirement under 8 CFR "
            "214.2(h)(4)(ii))"
        ),
    ),
    "COURSEWORK_AFTER_GRADUATION": CredentialFlagDefinition(
        type="COURSEWORK_AFTER_GRADUATION",
        severity="LOW",
        score=8,
        description=(
            "Transcript lists coursework dated after the claimed graduation date"
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Static reference data used by detectors.
# --------------------------------------------------------------------------- #


# Minimum plausible age at graduation per degree level.
MIN_GRAD_AGE: dict[str, int] = {
    "ASSOCIATE": 17,
    "BACHELOR": 19,
    "MASTER": 21,
    "PROFESSIONAL": 23,
    "DOCTORAL": 24,
}

# Minimum plausible enrollment-to-graduation years per degree level.
MIN_DEGREE_YEARS: dict[str, float] = {
    "ASSOCIATE": 1.5,
    "BACHELOR": 3.0,
    "MASTER": 1.0,
    "PROFESSIONAL": 2.0,
    "DOCTORAL": 2.5,
}

# Loose mapping of field-of-study keywords to SOC major groups for the
# specialty-occupation nexus check. Kept coarse on purpose: we only raise the
# flag when there is no overlap at all.
FIELD_TO_SOC_MAJOR: dict[str, set[str]] = {
    "computer": {"15"},
    "software": {"15"},
    "information systems": {"15"},
    "data": {"15"},
    "statistics": {"15", "19"},
    "mathematics": {"15", "19"},
    "electrical engineering": {"17", "15"},
    "mechanical engineering": {"17"},
    "civil engineering": {"17"},
    "chemical engineering": {"17", "19"},
    "biomedical": {"17", "19", "29"},
    "engineering": {"17", "15"},
    "physics": {"19"},
    "chemistry": {"19"},
    "biology": {"19", "29"},
    "nursing": {"29"},
    "medicine": {"29"},
    "pharmacy": {"29"},
    "finance": {"13"},
    "accounting": {"13"},
    "economics": {"13", "19"},
    "business": {"11", "13"},
    "management": {"11", "13"},
    "marketing": {"11", "13"},
    "law": {"23"},
    "english": {"27"},
    "literature": {"27"},
    "history": {"25"},
    "philosophy": {"25"},
    "sociology": {"19"},
    "psychology": {"19", "21"},
    "architecture": {"17"},
    "education": {"25"},
    "linguistics": {"27", "25"},
}


# Seed list of institutions publicly documented as diploma mills by the
# US Government Accountability Office, the Oregon Office of Degree
# Authorization, or state attorney general enforcement actions. Treat as a
# starting point; the production table is loaded via
# ``credentials/reference.py`` and kept current.
KNOWN_DIPLOMA_MILLS: tuple[tuple[str, str], ...] = (
    ("ALMEDA UNIVERSITY", "US"),
    ("BELFORD UNIVERSITY", "US"),
    ("BREYER STATE UNIVERSITY", "US"),
    ("CAPITOL UNIVERSITY", "US"),  # unrecognized, distinct from accredited institutions
    ("CONCORDIA COLLEGE AND UNIVERSITY", "US"),
    ("HAMILTON UNIVERSITY", "US"),
    ("KENNEDY WESTERN UNIVERSITY", "US"),
    ("LACROSSE UNIVERSITY", "US"),
    ("MADISON UNIVERSITY", "US"),
    ("PACIFIC WESTERN UNIVERSITY", "US"),
    ("RICHARDSON UNIVERSITY", "US"),
    ("ROCHVILLE UNIVERSITY", "US"),
    ("ST REGIS UNIVERSITY", "US"),
    ("SUFFIELD UNIVERSITY", "US"),
    ("TRINITY SOUTHERN UNIVERSITY", "US"),
    ("UNIVERSITY OF BERKLEY", "US"),
    ("UNIVERSITY OF NORTHERN WASHINGTON", "US"),
    ("WOODFIELD UNIVERSITY", "US"),
)


# NACES (naces.org) and AICE (aice-eval.org) member foreign-credential
# evaluators as of 2025. Listed here as a minimal seed; production data should
# be ingested from the two associations' published membership pages.
KNOWN_CRED_EVALUATORS: tuple[dict, ...] = (
    {"name": "WORLD EDUCATION SERVICES", "naces": True, "aice": False},
    {"name": "WES", "naces": True, "aice": False},
    {"name": "EDUCATIONAL CREDENTIAL EVALUATORS", "naces": True, "aice": False},
    {"name": "ECE", "naces": True, "aice": False},
    {"name": "INTERNATIONAL EDUCATION RESEARCH FOUNDATION", "naces": True, "aice": False},
    {"name": "IERF", "naces": True, "aice": False},
    {"name": "JOSEF SILNY AND ASSOCIATES", "naces": True, "aice": False},
    {"name": "SCHOLARO", "naces": True, "aice": False},
    {"name": "SPANTRAN", "naces": True, "aice": True},
    {"name": "TRUSTFORTE CORPORATION", "naces": True, "aice": False},
    {"name": "GLOBAL CREDENTIAL EVALUATORS", "naces": True, "aice": False},
    {"name": "ACADEMIC EVALUATION SERVICES", "naces": False, "aice": True},
    {"name": "CENTER FOR APPLIED RESEARCH EVALUATION AND EDUCATION", "naces": False, "aice": True},
    {"name": "EVALUATION SERVICE INC", "naces": False, "aice": True},
    {"name": "GLOBAL SERVICES ASSOCIATES", "naces": False, "aice": True},
)
