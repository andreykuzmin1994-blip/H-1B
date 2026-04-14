"""End-to-end scoring against an in-memory SQLite database."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    EntityRelationship,
    LcaFiling,
    SocWageBenchmark,
    SosEntity,
    UscisEmployerStats,
    Violation,
)
from h1b_engine.score.engine import score_all


@pytest.fixture
def seed_data(session_factory):
    session = session_factory()
    # Gas station filing software developer role at ~$31k (hard-flag mismatch)
    gas = Employer(
        name="Sunrise Convenience LLC",
        name_normalized="SUNRISE CONVENIENCE",
        state="GA",
        naics_code="447110",
        address_line1="1234 Memorial Dr",
        city="Decatur",
        zip="30032",
        total_lca_count=1,
        first_filing_date=date(2024, 1, 1),
        last_filing_date=date(2024, 1, 1),
        address_type="RESIDENTIAL",
    )
    session.add(gas)
    session.flush()
    session.add(
        LcaFiling(
            case_number="I-200-AAA",
            case_status="CERTIFIED",
            employer_id=gas.id,
            employer_name_raw="Sunrise Convenience LLC",
            naics_code="447110",
            soc_code="15-1252",
            soc_title="Software Developers",
            wage_from=15.00,
            wage_unit="Hour",
            wage_annualized=31200,
            prevailing_wage=62000,
            pw_unit="Year",
            pw_annualized=62000,
            wage_ratio=0.5,
            worksite_city="Decatur",
            worksite_state="GA",
            received_date=date(2024, 1, 1),
            fiscal_year=2024,
        )
    )
    # Legitimate software company for contrast (NAICS 511210 Software Publishers,
    # NOT 541512 which is staffing/consulting by our rule)
    legit = Employer(
        name="Acme Software",
        name_normalized="ACME SOFTWARE",
        state="CA",
        naics_code="511210",
        address_line1="1 Market St",
        city="San Francisco",
        zip="94105",
        total_lca_count=1,
        first_filing_date=date(2024, 1, 1),
        last_filing_date=date(2024, 1, 1),
        address_type="COMMERCIAL",
    )
    session.add(legit)
    session.flush()
    session.add(
        LcaFiling(
            case_number="I-200-BBB",
            case_status="CERTIFIED",
            employer_id=legit.id,
            naics_code="511210",
            soc_code="15-1252",
            soc_title="Software Developers",
            wage_from=170000,
            wage_unit="Year",
            wage_annualized=170000,
            prevailing_wage=150000,
            pw_unit="Year",
            pw_annualized=150000,
            wage_ratio=1.13,
            worksite_city="San Francisco",
            worksite_state="CA",
            received_date=date(2024, 1, 1),
            fiscal_year=2024,
        )
    )
    # BLS benchmark
    session.add(
        SocWageBenchmark(
            soc_code="15-1252",
            soc_title="Software Developers",
            oews_year=2024,
            area_type="NATIONAL",
            median_annual_wage=127000,
            mean_annual_wage=130000,
        )
    )
    session.commit()
    return session


def test_gas_station_flagged_legit_clean(session_factory, seed_data):
    score_all()
    session = session_factory()
    gas = session.execute(
        select(Employer).where(Employer.name_normalized == "SUNRISE CONVENIENCE")
    ).scalar_one()
    legit = session.execute(
        select(Employer).where(Employer.name_normalized == "ACME SOFTWARE")
    ).scalar_one()
    assert float(gas.anomaly_score) >= 40  # at least NAICS_SOC_MISMATCH
    assert float(legit.anomaly_score) == 0

    gas_flags = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == gas.id)
    ).scalars().all()
    flag_types = {f.flag_type for f in gas_flags}
    assert "NAICS_SOC_MISMATCH" in flag_types
    assert "WAGE_FAR_BELOW_SOC_MEDIAN" in flag_types
    assert "RESIDENTIAL_ADDRESS" in flag_types
    # Score capped at 100
    assert float(gas.anomaly_score) <= 100


def test_score_is_idempotent(session_factory, seed_data):
    score_all()
    score_all()
    session = session_factory()
    flags = session.execute(select(AnomalyFlag)).scalars().all()
    types = [f.flag_type for f in flags]
    # Each flag type should appear at most once per employer (no duplication on re-run)
    from collections import Counter

    counter = Counter((f.employer_id, f.flag_type) for f in flags)
    assert all(v == 1 for v in counter.values())


def test_post_sanction_flag_triggers(session_factory):
    session = session_factory()
    emp = Employer(
        name="Bad Actor LLC",
        name_normalized="BAD ACTOR",
        state="TX",
        naics_code="541512",
        total_lca_count=1,
        first_filing_date=date(2023, 1, 1),
        last_filing_date=date(2024, 1, 1),
    )
    session.add(emp)
    session.flush()
    session.add(
        LcaFiling(
            case_number="X1",
            employer_id=emp.id,
            received_date=date(2024, 6, 1),
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=150000,
        )
    )
    session.add(
        Violation(
            employer_id=emp.id,
            source="DOL_WILLFUL",
            violation_type="WILLFUL_VIOLATOR",
            violation_date=date(2023, 6, 1),
            debarment_start=date(2023, 6, 1),
            debarment_end=date(2025, 6, 1),
        )
    )
    session.commit()

    score_all()
    flags = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id)
    ).scalars().all()
    flag_types = {f.flag_type for f in flags}
    assert "POST_SANCTION_FILING" in flag_types


def test_new_entity_immediate_filing_multi_row(session_factory):
    """Confirm the detector scans ALL SosEntity rows (not just the first)."""
    session = session_factory()
    emp = Employer(
        name="Shell Holdings LLC",
        name_normalized="SHELL HOLDINGS",
        state="DE",
        naics_code="541512",
        total_lca_count=1,
        first_filing_date=date(2024, 1, 15),
        last_filing_date=date(2024, 1, 15),
    )
    session.add(emp)
    session.flush()
    session.add(
        LcaFiling(
            case_number="Z1",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=150000,
            received_date=date(2024, 1, 15),
            fiscal_year=2024,
        )
    )
    # First SOS row: formed 2+ years before first filing (too old, should NOT trigger)
    session.add(
        SosEntity(
            employer_id=emp.id,
            state="DE",
            entity_name="Shell Holdings LLC",
            entity_type="LLC",
            formation_date=date(2021, 1, 1),
        )
    )
    # Second SOS row: formed 30 days before first filing (WITHIN 90-day window)
    session.add(
        SosEntity(
            employer_id=emp.id,
            state="NV",
            entity_name="Shell Holdings NV LLC",
            entity_type="LLC",
            formation_date=date(2023, 12, 16),
        )
    )
    session.commit()

    score_all([emp.id])
    flags = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id)
    ).scalars().all()
    assert "NEW_ENTITY_IMMEDIATE_FILING" in {f.flag_type for f in flags}


def test_connected_to_violator_two_hops(session_factory):
    """A (no violations) connected to C (violator) via B: flag should fire at depth=2."""
    session = session_factory()

    def _mk(name: str, state: str) -> Employer:
        emp = Employer(
            name=name,
            name_normalized=name.upper(),
            state=state,
            naics_code="541512",
            total_lca_count=1,
            first_filing_date=date(2024, 1, 1),
            last_filing_date=date(2024, 1, 1),
        )
        session.add(emp)
        session.flush()
        session.add(
            LcaFiling(
                case_number=f"CASE-{name}",
                employer_id=emp.id,
                naics_code="541512",
                soc_code="15-1252",
                wage_annualized=150000,
                received_date=date(2024, 1, 1),
                fiscal_year=2024,
            )
        )
        return emp

    a = _mk("alpha co", "WA")
    b = _mk("bravo co", "OR")
    c = _mk("charlie co", "ID")

    # A-B shared address (depth 1 from A), B-C shared officer (depth 2 from A)
    session.add_all(
        [
            EntityRelationship(
                employer_id_a=min(a.id, b.id),
                employer_id_b=max(a.id, b.id),
                relationship_type="SHARED_ADDRESS",
                confidence=0.6,
            ),
            EntityRelationship(
                employer_id_a=min(b.id, c.id),
                employer_id_b=max(b.id, c.id),
                relationship_type="SHARED_OFFICER",
                confidence=1.0,
            ),
        ]
    )
    # C is the violator
    session.add(
        Violation(
            employer_id=c.id,
            source="DOL_WILLFUL",
            violation_type="WILLFUL_VIOLATOR",
            violation_date=date(2023, 1, 1),
        )
    )
    session.commit()

    score_all([a.id])
    flags = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == a.id)
    ).scalars().all()
    connected = [f for f in flags if f.flag_type == "CONNECTED_TO_VIOLATOR"]
    assert len(connected) == 1
    evidence = connected[0].evidence or {}
    assert evidence.get("violator_employer_id") == c.id
    assert evidence.get("depth") == 2


def test_business_park_not_shared_address_cluster(session_factory):
    """A business-park address should NOT produce a SHARED_ADDRESS_CLUSTER flag."""
    session = session_factory()
    for i in range(6):
        emp = Employer(
            name=f"Tenant {i} LLC",
            name_normalized=f"TENANT {i}",
            state="TX",
            naics_code="541512",
            address_line1="100 Crosswinds Business Park",
            city="Austin",
            zip="78701",
            total_lca_count=1,
            first_filing_date=date(2024, 1, 1),
            last_filing_date=date(2024, 1, 1),
        )
        session.add(emp)
    session.commit()
    score_all()
    flags = session.execute(select(AnomalyFlag)).scalars().all()
    assert not any(f.flag_type == "SHARED_ADDRESS_CLUSTER" for f in flags)
