"""Tests for the retained fraud-detection triggers.

Covers:
- COMMON_AGENT_CLUSTER
- OFFICER_PRIOR_VISA_INDICTMENT
- DOL_BENCHING_COMPLAINT_HISTORY
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    SosEntity,
    Violation,
)
from h1b_engine.score.engine import score_all
from h1b_engine.score.reference import (
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
# COMMON_AGENT_CLUSTER
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
# OFFICER_PRIOR_VISA_INDICTMENT
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
# DOL_BENCHING_COMPLAINT_HISTORY
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
