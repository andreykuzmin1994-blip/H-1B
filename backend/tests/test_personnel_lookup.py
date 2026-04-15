"""Tests for the Personnel Look-Up / credential verification tool."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from h1b_engine.credentials.lookup import (
    bootstrap,
    lookup_by_name,
    lookup_personnel,
    verify_all_for_employer,
    verify_credentials,
)
from h1b_engine.credentials.reference import upsert_university
from h1b_engine.db.models import (
    Beneficiary,
    CredentialClaim,
    CredentialFlag,
    Employer,
    LcaFiling,
    University,
    UniversityProgram,
    UniversitySignatory,
    Violation,
)
from h1b_engine.utils.names import normalize_employer_name


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _mk_employer(session, name, state="CA", naics="541512") -> Employer:
    e = Employer(
        name=name,
        name_normalized=normalize_employer_name(name),
        state=state,
        naics_code=naics,
        total_lca_count=1,
        first_filing_date=date(2024, 1, 1),
        last_filing_date=date(2024, 1, 1),
    )
    session.add(e)
    session.flush()
    return e


def _mk_beneficiary(session, employer, name, dob, **kwargs) -> Beneficiary:
    b = Beneficiary(
        employer_id=employer.id if employer else None,
        full_name=name,
        name_normalized=normalize_employer_name(name),
        date_of_birth=dob,
        source=kwargs.pop("source", "TIP"),
        **kwargs,
    )
    session.add(b)
    session.flush()
    return b


@pytest.fixture
def reference(session_factory):
    """Fresh in-memory DB with the reference-data seed loaded."""
    session = session_factory()
    bootstrap(session=session)
    # Seed a good and bad institution.
    good = upsert_university(
        session,
        name="Stanford University",
        country="US",
        accreditation_status="ACCREDITED",
        state="CA",
        founded_year=1891,
        official_domain="stanford.edu",
    )
    session.add_all(
        [
            UniversityProgram(
                university_id=good.id,
                degree_level="BACHELOR",
                program_name="Computer Science",
                program_name_normalized=normalize_employer_name("Computer Science"),
                first_conferred_year=1970,
            ),
            UniversityProgram(
                university_id=good.id,
                degree_level="MASTER",
                program_name="Computer Science",
                program_name_normalized=normalize_employer_name("Computer Science"),
                first_conferred_year=1970,
            ),
            UniversitySignatory(
                university_id=good.id,
                full_name="Dean Jane Smith",
                name_normalized=normalize_employer_name("Dean Jane Smith"),
                title="Registrar",
                email="jsmith@stanford.edu",
                active_from=date(2010, 1, 1),
                active_until=date(2030, 1, 1),
            ),
            UniversitySignatory(
                university_id=good.id,
                full_name="Dr John Doe",
                name_normalized=normalize_employer_name("Dr John Doe"),
                title="Emeritus Professor",
                active_from=date(1970, 1, 1),
                active_until=date(2005, 6, 30),
                is_deceased=1,
            ),
        ]
    )
    # A community college that only offers Associate's — used to test the
    # DEGREE_LEVEL_NOT_OFFERED detector.
    cc = upsert_university(
        session,
        name="Foothill College",
        country="US",
        accreditation_status="ACCREDITED",
        state="CA",
    )
    session.add(
        UniversityProgram(
            university_id=cc.id,
            degree_level="ASSOCIATE",
            program_name="General Studies",
            program_name_normalized=normalize_employer_name("General Studies"),
        )
    )
    session.commit()
    return session


# --------------------------------------------------------------------------- #
# Reference / bootstrap
# --------------------------------------------------------------------------- #


def test_bootstrap_seeds_diploma_mills_and_evaluators(session_factory):
    session = session_factory()
    bootstrap(session=session)
    mills = session.execute(
        select(University).where(University.accreditation_status == "DIPLOMA_MILL")
    ).scalars().all()
    assert len(mills) > 5
    assert any("BELFORD" in m.name.upper() for m in mills)


# --------------------------------------------------------------------------- #
# University existence / accreditation
# --------------------------------------------------------------------------- #


def test_university_not_found_flag_fires(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Acme Software")
    b = _mk_beneficiary(
        session, emp, "Alice Applicant", dob=date(1995, 5, 1),
        country_of_citizenship="IN",
    )
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Institute of Fictional Learning",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2017, 6, 1),
        )
    )
    session.commit()

    report = lookup_personnel(b.id, session=session)
    types = {f.type for f in report.flags}
    assert "UNIVERSITY_NOT_FOUND" in types


def test_diploma_mill_flag_fires(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Mill Test Co")
    b = _mk_beneficiary(session, emp, "Bob Beneficiary", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Belford University",
            country="US",
            degree_level="MASTER",
            field_of_study="Computer Science",
            graduation_date=date(2018, 5, 1),
        )
    )
    session.commit()

    report = lookup_personnel(b.id, session=session)
    types = {f.type for f in report.flags}
    assert "DIPLOMA_MILL_UNIVERSITY" in types
    critical_flags = [f for f in report.flags if f.severity == "CRITICAL"]
    assert critical_flags, "diploma-mill hit should carry a CRITICAL flag"


def test_university_founded_after_graduation(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Timeline Co")
    b = _mk_beneficiary(session, emp, "Carla Claim", dob=date(1950, 1, 1))
    # Stanford was founded 1891; claim graduation in 1850.
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(1850, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    types = {f.type for f in report.flags}
    assert "UNIVERSITY_FOUNDED_AFTER_GRADUATION" in types


# --------------------------------------------------------------------------- #
# Degree program / level
# --------------------------------------------------------------------------- #


def test_degree_level_not_offered(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "CC Test Co")
    b = _mk_beneficiary(session, emp, "Derek Degree", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Foothill College",
            country="US",
            degree_level="DOCTORAL",
            field_of_study="Philosophy",
            graduation_date=date(2018, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "DEGREE_LEVEL_NOT_OFFERED" for f in report.flags)


def test_degree_not_offered_by_field(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Field Test Co")
    b = _mk_beneficiary(session, emp, "Eva Engineer", dob=date(1990, 1, 1))
    # Stanford only seeded with CS programs — claim Biomedical Eng (no match).
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Biomedical Engineering",
            graduation_date=date(2015, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "DEGREE_NOT_OFFERED" for f in report.flags)


# --------------------------------------------------------------------------- #
# Signatory
# --------------------------------------------------------------------------- #


def test_signatory_not_at_university(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Sig Test Co")
    b = _mk_beneficiary(session, emp, "Sam Signer", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2015, 6, 1),
            signatory_name_raw="Imposter McFake",
            signatory_title_raw="Registrar",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "SIGNATORY_NOT_AT_UNIVERSITY" for f in report.flags)


def test_signatory_deceased_at_signing_date(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Ghost Signer Co")
    b = _mk_beneficiary(session, emp, "Tara Timeline", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2015, 6, 1),  # Dr John Doe died 2005
            signatory_name_raw="Dr John Doe",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "SIGNATORY_DECEASED_AT_SIGN_DATE" for f in report.flags)


def test_signatory_email_domain_mismatch(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Domain Test Co")
    b = _mk_beneficiary(session, emp, "Dana Domain", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2015, 6, 1),
            signatory_name_raw="Dean Jane Smith",
            signatory_email_raw="jsmith@gmail.com",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "SIGNATORY_EMAIL_DOMAIN_MISMATCH" for f in report.flags)


def test_signatory_clean_path_has_no_flag(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Clean Co")
    b = _mk_beneficiary(session, emp, "Ok Ok", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2015, 6, 1),
            signatory_name_raw="Dean Jane Smith",
            signatory_email_raw="jsmith@stanford.edu",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    types = {f.type for f in report.flags}
    assert "SIGNATORY_NOT_AT_UNIVERSITY" not in types
    assert "SIGNATORY_EMAIL_DOMAIN_MISMATCH" not in types


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #


def test_impossible_graduation_before_birth(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Time Loop Co")
    b = _mk_beneficiary(session, emp, "Timmy Travel", dob=date(2000, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(1990, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "IMPOSSIBLE_GRADUATION_DATE" for f in report.flags)


def test_underage_degree_fires(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Underage Co")
    b = _mk_beneficiary(session, emp, "Young Grad", dob=date(2010, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2021, 6, 1),  # age ~11
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "UNDERAGE_DEGREE" for f in report.flags)


def test_enrollment_after_graduation(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Rev Time Co")
    b = _mk_beneficiary(session, emp, "Rev Timer", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            enrollment_start_date=date(2018, 1, 1),
            graduation_date=date(2016, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "ENROLLMENT_AFTER_GRADUATION" for f in report.flags)


# --------------------------------------------------------------------------- #
# Evaluator / identity / SOC mismatch
# --------------------------------------------------------------------------- #


def test_evaluator_unknown(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Eval Co")
    b = _mk_beneficiary(session, emp, "Eli Evaluated", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="EVALUATION",
            evaluator_organization_raw="Joe's Mom Credential Service",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "EVALUATOR_UNKNOWN" for f in report.flags)


def test_known_naces_evaluator_clean(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "WES User Co")
    b = _mk_beneficiary(session, emp, "Wes User", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="EVALUATION",
            evaluator_organization_raw="World Education Services",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    types = {f.type for f in report.flags}
    assert "EVALUATOR_UNKNOWN" not in types
    assert "EVALUATOR_NOT_ACCREDITED" not in types


def test_duplicate_identity_across_employers(session_factory, reference):
    session = session_factory()
    emp_a = _mk_employer(session, "Alpha Co", state="CA")
    emp_b = _mk_employer(session, "Beta Co", state="NY")
    dob = date(1990, 1, 1)
    b1 = _mk_beneficiary(session, emp_a, "Dupe Identity", dob=dob)
    b2 = _mk_beneficiary(session, emp_b, "Dupe Identity", dob=dob)
    session.commit()

    report = lookup_personnel(b1.id, session=session)
    assert any(
        f.type == "DUPLICATE_BENEFICIARY_IDENTITY" for f in report.flags
    )


def test_passport_reuse_across_names(session_factory, reference):
    session = session_factory()
    emp_a = _mk_employer(session, "Passport A Co", state="CA")
    emp_b = _mk_employer(session, "Passport B Co", state="NY")
    b1 = _mk_beneficiary(
        session,
        emp_a,
        "Name One",
        dob=date(1990, 1, 1),
        passport_last4="1234",
        passport_country="IN",
    )
    _mk_beneficiary(
        session,
        emp_b,
        "Completely Different Person",
        dob=date(1991, 1, 1),
        passport_last4="1234",
        passport_country="IN",
    )
    session.commit()

    report = lookup_personnel(b1.id, session=session)
    assert any(f.type == "PASSPORT_NUMBER_REUSE" for f in report.flags)


def test_debarred_employer_flag(session_factory, reference):
    session = session_factory()
    bad = _mk_employer(session, "Debarred Co", state="TX")
    session.add(
        Violation(
            employer_id=bad.id,
            source="DOL_WILLFUL",
            violation_type="WILLFUL_VIOLATOR",
            violation_date=date(2022, 1, 1),
        )
    )
    good = _mk_employer(session, "Current Sponsor Co", state="CA")
    dob = date(1988, 1, 1)
    _mk_beneficiary(session, bad, "Reused Person", dob=dob)
    b_current = _mk_beneficiary(session, good, "Reused Person", dob=dob)
    session.commit()

    report = lookup_personnel(b_current.id, session=session)
    assert any(
        f.type == "BENEFICIARY_ON_DEBARRED_EMPLOYER" for f in report.flags
    )


def test_degree_field_soc_mismatch(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "SOC Mismatch Co")
    # Attach an LCA with SOC for software developers.
    lca = LcaFiling(
        case_number="I-200-SOC-1",
        employer_id=emp.id,
        soc_code="15-1252",
        soc_title="Software Developers",
        received_date=date(2024, 1, 1),
        wage_annualized=150000,
        fiscal_year=2024,
    )
    session.add(lca)
    session.flush()
    b = _mk_beneficiary(
        session, emp, "Lit Literature", dob=date(1990, 1, 1), lca_filing_id=lca.id
    )
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="English Literature",
            graduation_date=date(2012, 6, 1),
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert any(f.type == "DEGREE_FIELD_SOC_MISMATCH" for f in report.flags)


# --------------------------------------------------------------------------- #
# Orchestration / persistence
# --------------------------------------------------------------------------- #


def test_verify_credentials_is_idempotent(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Idem Co")
    b = _mk_beneficiary(session, emp, "Idem User", dob=date(1990, 1, 1))
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Belford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            graduation_date=date(2015, 6, 1),
        )
    )
    session.commit()

    verify_credentials(b.id, session=session)
    verify_credentials(b.id, session=session)
    flags = session.execute(
        select(CredentialFlag).where(CredentialFlag.beneficiary_id == b.id)
    ).scalars().all()
    types = [f.flag_type for f in flags]
    # No duplicate flag rows even after two runs.
    assert len(types) == len(set(types))


def test_lookup_by_name(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "NameLook Co")
    _mk_beneficiary(session, emp, "Query Match", dob=date(1990, 1, 1))
    session.commit()
    reports = lookup_by_name("query match", session=session)
    assert len(reports) == 1
    assert reports[0].full_name == "Query Match"


def test_verify_all_for_employer_returns_reports(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Batch Co")
    for i in range(3):
        _mk_beneficiary(session, emp, f"Worker {i}", dob=date(1990, 1, 1))
    session.commit()
    reports = verify_all_for_employer(emp.id, session=session)
    assert len(reports) == 3
    assert all(r.employer_id == emp.id for r in reports)


def test_clean_claim_produces_no_flags(session_factory, reference):
    session = session_factory()
    emp = _mk_employer(session, "Clean Path Co")
    b = _mk_beneficiary(
        session,
        emp,
        "Alice Clean",
        dob=date(1990, 6, 1),
        country_of_citizenship="IN",
    )
    session.add(
        CredentialClaim(
            beneficiary_id=b.id,
            claim_type="DEGREE",
            university_name_raw="Stanford University",
            country="US",
            degree_level="BACHELOR",
            field_of_study="Computer Science",
            enrollment_start_date=date(2008, 9, 1),
            graduation_date=date(2012, 6, 1),
            signatory_name_raw="Dean Jane Smith",
            signatory_email_raw="jsmith@stanford.edu",
        )
    )
    session.commit()
    report = lookup_personnel(b.id, session=session)
    assert report.total_score == 0
    assert report.flags == []
