"""Test investigation report generation on a seeded employer."""
from __future__ import annotations

from datetime import date

import pytest

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    LcaFiling,
    SocWageBenchmark,
    UscisEmployerStats,
)
from h1b_engine.investigate.report import generate_report, tip_text


@pytest.fixture
def seeded(session_factory):
    s = session_factory()
    emp = Employer(
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
        anomaly_score=85,
        address_type="RESIDENTIAL",
    )
    s.add(emp)
    s.flush()
    s.add(
        LcaFiling(
            case_number="I-200-AAA",
            case_status="CERTIFIED",
            employer_id=emp.id,
            naics_code="447110",
            soc_code="15-1252",
            soc_title="Software Developers",
            wage_annualized=31200,
            wage_from=15,
            wage_unit="Hour",
            prevailing_wage=62000,
            pw_unit="Year",
            pw_annualized=62000,
            received_date=date(2024, 1, 1),
            fiscal_year=2024,
        )
    )
    s.add(
        AnomalyFlag(
            employer_id=emp.id,
            flag_type="NAICS_SOC_MISMATCH",
            flag_severity="CRITICAL",
            flag_score=40,
            description="Gas station filing for software developer role",
            evidence={"naics": "447110", "soc_code": "15-1252"},
        )
    )
    s.add(
        UscisEmployerStats(
            employer_id=emp.id,
            fiscal_year=2024,
            initial_approvals=4,
            initial_denials=7,
        )
    )
    s.add(
        SocWageBenchmark(
            soc_code="15-1252",
            oews_year=2024,
            area_type="NATIONAL",
            median_annual_wage=127000,
        )
    )
    s.commit()
    return emp


def test_generate_report_contains_key_sections(seeded):
    text = generate_report(seeded.id)
    assert "EMPLOYER INVESTIGATION REPORT" in text
    assert "ANOMALY FLAGS" in text
    assert "FILING HISTORY" in text
    assert "USCIS PETITION OUTCOMES" in text
    assert "WAGE BENCHMARK ANALYSIS" in text
    assert "RECOMMENDED ACTION" in text
    assert "Sunrise Convenience" in text
    assert "NAICS_SOC_MISMATCH" in text


def test_tip_text_contains_complaint_blocks(seeded):
    text = tip_text(seeded.id)
    assert "DOL WH-4 COMPLAINT" in text
    assert "USCIS TIP" in text
    assert "Sunrise Convenience" in text
