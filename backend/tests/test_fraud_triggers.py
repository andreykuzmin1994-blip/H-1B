"""Tests for the six new fraud-detection triggers (tranche 1-6).

Covers:
- MULTI_REGISTRATION_SAME_BENEFICIARY
- COMMON_AGENT_CLUSTER
- OFFICER_PRIOR_VISA_INDICTMENT
- NO_PAYROLL_FOR_H1B_VOLUME
- PREPARER_ON_EOIR_DISCIPLINE_LIST
- DOL_BENCHING_COMPLAINT_HISTORY
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from h1b_engine.db.models import (
    AnomalyFlag,
    DisciplinedPractitioner,
    Employer,
    EmployerPayrollRecord,
    EntityRelationship,
    H1BRegistration,
    LcaFiling,
    SosEntity,
    UscisEmployerStats,
    Violation,
)
from h1b_engine.score.engine import score_all
from h1b_engine.score.reference import (
    add_disciplined_practitioners,
    bootstrap_score_reference,
    seed_fraud_defendants,
)
from h1b_engine.utils.names import normalize_employer_name


def _mk_employer(session, name, state="CA", naics="541512") -> Employer:
    emp = Employer(
        name=name,
        name_normalized=normalize_employer_name(name),
        state=state,
        naics_code=naics,
        total_lca_count=0,
        first_filing_date=date(2024, 1, 1),
        last_filing_date=date(2024, 1, 1),
    )
    session.add(emp)
    session.flush()
    return emp


def _flag_types_for(session, employer_id) -> set[str]:
    rows = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == employer_id)
    ).scalars().all()
    return {f.flag_type for f in rows}


# --------------------------------------------------------------------------- #
# 1. MULTI_REGISTRATION_SAME_BENEFICIARY
# --------------------------------------------------------------------------- #


def test_multi_registration_flag_fires_across_unrelated_employers(session_factory):
    session = session_factory()
    emp_a = _mk_employer(session, "Petitioner A")
    emp_b = _mk_employer(session, "Petitioner B", state="NY")
    # Same beneficiary (name+DOB) registered by both petitioners in FY2026 cap.
    for emp in (emp_a, emp_b):
        session.add(
            H1BRegistration(
                employer_id=emp.id,
                employer_name_raw=emp.name,
                cap_fiscal_year=2026,
                beneficiary_full_name="Priya Kumar",
                beneficiary_name_normalized=normalize_employer_name("Priya Kumar"),
                beneficiary_date_of_birth=date(1995, 4, 1),
                status="SUBMITTED",
            )
        )
    session.commit()
    score_all([emp_a.id, emp_b.id])
    assert "MULTI_REGISTRATION_SAME_BENEFICIARY" in _flag_types_for(
        session, emp_a.id
    )
    assert "MULTI_REGISTRATION_SAME_BENEFICIARY" in _flag_types_for(
        session, emp_b.id
    )


def test_multi_registration_suppressed_for_related_employers(session_factory):
    session = session_factory()
    parent = _mk_employer(session, "Parent Co")
    sub = _mk_employer(session, "Parent Subsidiary", state="NY")
    # Known affiliation in the entity graph.
    session.add(
        EntityRelationship(
            employer_id_a=min(parent.id, sub.id),
            employer_id_b=max(parent.id, sub.id),
            relationship_type="SHARED_OFFICER",
            confidence=1.0,
        )
    )
    for emp in (parent, sub):
        session.add(
            H1BRegistration(
                employer_id=emp.id,
                employer_name_raw=emp.name,
                cap_fiscal_year=2026,
                beneficiary_full_name="Asha Reddy",
                beneficiary_name_normalized=normalize_employer_name("Asha Reddy"),
                beneficiary_date_of_birth=date(1992, 10, 3),
            )
        )
    session.commit()
    score_all([parent.id, sub.id])
    assert "MULTI_REGISTRATION_SAME_BENEFICIARY" not in _flag_types_for(
        session, parent.id
    )


def test_multi_registration_by_passport(session_factory):
    session = session_factory()
    emp_a = _mk_employer(session, "Pass A Co")
    emp_b = _mk_employer(session, "Pass B Co", state="TX")
    # Different transliterations of the same name, same passport.
    session.add(
        H1BRegistration(
            employer_id=emp_a.id,
            cap_fiscal_year=2026,
            beneficiary_full_name="Muhammad Ali",
            beneficiary_name_normalized=normalize_employer_name("Muhammad Ali"),
            beneficiary_date_of_birth=date(1990, 1, 1),
            passport_last4="9876",
            passport_country="PK",
        )
    )
    session.add(
        H1BRegistration(
            employer_id=emp_b.id,
            cap_fiscal_year=2026,
            beneficiary_full_name="Mohammed Aly",
            beneficiary_name_normalized=normalize_employer_name("Mohammed Aly"),
            beneficiary_date_of_birth=date(1990, 1, 1),
            passport_last4="9876",
            passport_country="PK",
        )
    )
    session.commit()
    score_all([emp_a.id, emp_b.id])
    assert "MULTI_REGISTRATION_SAME_BENEFICIARY" in _flag_types_for(
        session, emp_a.id
    )


# --------------------------------------------------------------------------- #
# 2. COMMON_AGENT_CLUSTER
# --------------------------------------------------------------------------- #


def test_common_agent_cluster_fires_at_three(session_factory):
    session = session_factory()
    emps = [
        _mk_employer(session, f"Shell {i} LLC", state="DE")
        for i in range(3)
    ]
    for emp in emps:
        session.add(
            SosEntity(
                employer_id=emp.id,
                state="DE",
                entity_name=emp.name,
                entity_type="LLC",
                formation_date=date(2023, 1, 1),
                registered_agent="Delaware Agent Services Inc",
                principal_address="100 Corporate Blvd, Wilmington, DE 19801",
            )
        )
    session.commit()
    score_all([e.id for e in emps])
    for emp in emps:
        types = _flag_types_for(session, emp.id)
        assert "COMMON_AGENT_CLUSTER" in types


def test_common_agent_cluster_does_not_fire_below_threshold(session_factory):
    session = session_factory()
    emps = [
        _mk_employer(session, f"PairOnly {i} LLC", state="DE")
        for i in range(2)
    ]
    for emp in emps:
        session.add(
            SosEntity(
                employer_id=emp.id,
                state="DE",
                entity_name=emp.name,
                registered_agent="Acme Agent Co",
                principal_address="500 Main St, Dover, DE",
            )
        )
    session.commit()
    score_all([e.id for e in emps])
    for emp in emps:
        assert "COMMON_AGENT_CLUSTER" not in _flag_types_for(session, emp.id)


# --------------------------------------------------------------------------- #
# 3. OFFICER_PRIOR_VISA_INDICTMENT
# --------------------------------------------------------------------------- #


def test_officer_prior_visa_indictment_flag(session_factory):
    session = session_factory()
    seed_fraud_defendants(session)
    emp = _mk_employer(session, "Successor LLC")
    session.add(
        SosEntity(
            employer_id=emp.id,
            state="DE",
            entity_name="Successor LLC",
            officers=[
                {"name": "Innocent Bystander", "title": "CEO"},
                # One of the seeded Nanosemantics defendants.
                {"name": "Kishore Dattapuram", "title": "Managing Member"},
            ],
        )
    )
    session.commit()
    score_all([emp.id])
    flags = session.execute(
        select(AnomalyFlag).where(
            AnomalyFlag.employer_id == emp.id,
            AnomalyFlag.flag_type == "OFFICER_PRIOR_VISA_INDICTMENT",
        )
    ).scalars().all()
    assert len(flags) == 1
    ev = flags[0].evidence or {}
    assert ev.get("matched_officer") == "Kishore Dattapuram"
    assert ev.get("matched_cases")


def test_officer_indictment_flag_silent_when_no_match(session_factory):
    session = session_factory()
    seed_fraud_defendants(session)
    emp = _mk_employer(session, "Clean Org LLC")
    session.add(
        SosEntity(
            employer_id=emp.id,
            state="DE",
            officers=[{"name": "Jane Clean", "title": "CEO"}],
        )
    )
    session.commit()
    score_all([emp.id])
    assert "OFFICER_PRIOR_VISA_INDICTMENT" not in _flag_types_for(session, emp.id)


# --------------------------------------------------------------------------- #
# 4. NO_PAYROLL_FOR_H1B_VOLUME
# --------------------------------------------------------------------------- #


def test_no_payroll_flag_fires_when_approvals_vastly_exceed_workers(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "Ghost Ghost LLC")
    session.add(
        UscisEmployerStats(
            employer_id=emp.id,
            fiscal_year=2024,
            initial_approvals=50,
            initial_denials=0,
        )
    )
    session.add(
        EmployerPayrollRecord(
            employer_id=emp.id,
            fiscal_year=2024,
            source="QCEW",
            worker_count=2,
            total_wages=120_000,
        )
    )
    session.commit()
    score_all([emp.id])
    assert "NO_PAYROLL_FOR_H1B_VOLUME" in _flag_types_for(session, emp.id)


def test_no_payroll_flag_fires_when_payroll_record_missing(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "No Payroll Co")
    session.add(
        UscisEmployerStats(
            employer_id=emp.id,
            fiscal_year=2024,
            initial_approvals=20,
            initial_denials=0,
        )
    )
    session.commit()
    score_all([emp.id])
    assert "NO_PAYROLL_FOR_H1B_VOLUME" in _flag_types_for(session, emp.id)


def test_no_payroll_flag_silent_under_volume_threshold(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "Small Co")
    session.add(
        UscisEmployerStats(
            employer_id=emp.id,
            fiscal_year=2024,
            initial_approvals=2,  # below PAYROLL_GAP_MIN_APPROVALS
            initial_denials=0,
        )
    )
    session.commit()
    score_all([emp.id])
    assert "NO_PAYROLL_FOR_H1B_VOLUME" not in _flag_types_for(session, emp.id)


def test_no_payroll_flag_silent_when_workforce_matches(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "Honest Co")
    session.add(
        UscisEmployerStats(
            employer_id=emp.id,
            fiscal_year=2024,
            initial_approvals=20,
            initial_denials=0,
        )
    )
    session.add(
        EmployerPayrollRecord(
            employer_id=emp.id,
            fiscal_year=2024,
            source="QCEW",
            worker_count=200,
            total_wages=30_000_000,
        )
    )
    session.commit()
    score_all([emp.id])
    assert "NO_PAYROLL_FOR_H1B_VOLUME" not in _flag_types_for(session, emp.id)


# --------------------------------------------------------------------------- #
# 5. PREPARER_ON_EOIR_DISCIPLINE_LIST
# --------------------------------------------------------------------------- #


def test_preparer_discipline_flag_fires(session_factory):
    session = session_factory()
    add_disciplined_practitioners(
        session,
        [
            {
                "full_name": "Disbarred Dan",
                "bar_id": "NY-12345",
                "jurisdiction": "NY",
                "discipline_type": "DISBARMENT",
                "effective_date": date(2023, 1, 1),
                "source_url": "https://www.justice.gov/eoir/list-of-currently-disciplined-practitioners",
            }
        ],
    )
    emp = _mk_employer(session, "Disciplined Client LLC")
    session.add(
        LcaFiling(
            case_number="I-200-DISC",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=160_000,
            received_date=date(2024, 1, 1),
            fiscal_year=2024,
            attorney_name="Disbarred Dan",
            attorney_name_normalized=normalize_employer_name("Disbarred Dan"),
            attorney_firm="Dan Law LLP",
        )
    )
    session.commit()
    score_all([emp.id])
    assert "PREPARER_ON_EOIR_DISCIPLINE_LIST" in _flag_types_for(session, emp.id)


def test_preparer_discipline_flag_silent_for_clean_attorney(session_factory):
    session = session_factory()
    add_disciplined_practitioners(
        session,
        [
            {
                "full_name": "Disbarred Dan",
                "bar_id": "NY-12345",
                "discipline_type": "DISBARMENT",
            }
        ],
    )
    emp = _mk_employer(session, "Clean Attorney LLC")
    session.add(
        LcaFiling(
            case_number="I-200-CLEAN",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=160_000,
            received_date=date(2024, 1, 1),
            fiscal_year=2024,
            attorney_name="Upstanding Clarissa",
            attorney_name_normalized=normalize_employer_name("Upstanding Clarissa"),
        )
    )
    session.commit()
    score_all([emp.id])
    assert "PREPARER_ON_EOIR_DISCIPLINE_LIST" not in _flag_types_for(session, emp.id)


# --------------------------------------------------------------------------- #
# 6. DOL_BENCHING_COMPLAINT_HISTORY
# --------------------------------------------------------------------------- #


def test_dol_benching_flag_fires(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "Benching Firm LLC")
    session.add(
        Violation(
            employer_id=emp.id,
            source="WHD_ENFORCEMENT",
            violation_type="H1B NONPRODUCTIVE STATUS WAGE",
            violation_date=date(2023, 5, 1),
            back_wages_amount=45_000,
            description="Employer failed to pay required wage during nonproductive benching period.",
        )
    )
    session.commit()
    score_all([emp.id])
    assert "DOL_BENCHING_COMPLAINT_HISTORY" in _flag_types_for(session, emp.id)


def test_dol_benching_flag_silent_for_unrelated_violation(session_factory):
    session = session_factory()
    emp = _mk_employer(session, "Other Violation LLC")
    session.add(
        Violation(
            employer_id=emp.id,
            source="WHD_ENFORCEMENT",
            violation_type="RECORDKEEPING",
            violation_date=date(2023, 5, 1),
            description="Public access file incomplete.",
        )
    )
    session.commit()
    score_all([emp.id])
    assert "DOL_BENCHING_COMPLAINT_HISTORY" not in _flag_types_for(session, emp.id)


# --------------------------------------------------------------------------- #
# Bootstrap / integration sanity
# --------------------------------------------------------------------------- #


def test_bootstrap_score_reference_is_idempotent(session_factory):
    session = session_factory()
    first = bootstrap_score_reference(session)
    session.commit()
    second = bootstrap_score_reference(session)
    assert first["fraud_defendants"][0] > 0  # first run inserts
    assert second["fraud_defendants"][0] == 0  # second run only updates


def test_new_triggers_are_idempotent_across_reruns(session_factory):
    session = session_factory()
    seed_fraud_defendants(session)
    emp = _mk_employer(session, "Idem Trigger Co")
    session.add(
        SosEntity(
            employer_id=emp.id,
            officers=[{"name": "Kishore Dattapuram", "title": "CEO"}],
        )
    )
    session.add(
        Violation(
            employer_id=emp.id,
            source="WHD_ENFORCEMENT",
            violation_type="BENCHING",
            description="Benched workers.",
        )
    )
    session.commit()
    score_all([emp.id])
    score_all([emp.id])
    from collections import Counter

    rows = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id)
    ).scalars().all()
    counts = Counter((r.employer_id, r.flag_type) for r in rows)
    assert all(v == 1 for v in counts.values())
