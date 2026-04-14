"""End-to-end scoring against an in-memory SQLite database."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    LcaFiling,
    SocWageBenchmark,
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
