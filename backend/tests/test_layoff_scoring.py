"""Tests for the layoffs + concurrent H-1B filing detectors."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from h1b_engine.db.models import AnomalyFlag, Employer, LayoffEvent, LcaFiling
from h1b_engine.investigate.report import generate_report, tip_text
from h1b_engine.score.engine import score_all


def _build_employer(session, *, name: str, state: str = "CA") -> Employer:
    emp = Employer(
        name=name,
        name_normalized=name.upper(),
        state=state,
        naics_code="541512",
        total_lca_count=1,
        first_filing_date=date(2026, 1, 1),
        last_filing_date=date(2026, 1, 1),
    )
    session.add(emp)
    session.flush()
    return emp


def test_layoff_base_flag_fires_inside_90_day_window(session_factory):
    session = session_factory()
    emp = _build_employer(session, name="Oracle Corp")
    session.add(
        LcaFiling(
            case_number="I-200-LAYOFF-1",
            case_status="CERTIFIED",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            soc_title="Software Developers",
            wage_annualized=160_000,
            worksite_city="Austin",
            worksite_state="TX",
            received_date=date(2026, 3, 1),
            fiscal_year=2026,
        )
    )
    session.add(
        LayoffEvent(
            employer_id=emp.id,
            employer_name_raw="Oracle Corp",
            source="WARN_STATE_TX",
            effective_date=date(2026, 4, 15),  # 45 days after the LCA
            workers_affected=500,
            location_city="Austin",
            location_state="TX",
            reason="Permanent software engineering reduction",
        )
    )
    session.commit()

    score_all([emp.id])

    flags = session_factory().execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id)
    ).scalars().all()
    types = {f.flag_type for f in flags}
    assert "LAYOFF_WITH_CONCURRENT_H1B" in types
    assert "LAYOFF_SAME_WORKSITE_H1B" in types  # city+state match
    assert "LAYOFF_SAME_SOC_H1B" in types  # reason "software engineering" -> SOC major 15
    base = next(f for f in flags if f.flag_type == "LAYOFF_WITH_CONCURRENT_H1B")
    assert base.evidence["days_between"] == 45
    assert base.evidence["direction"] == "before_layoff"
    assert base.evidence["lca_case_number"] == "I-200-LAYOFF-1"


def test_layoff_flag_not_fired_outside_window(session_factory):
    session = session_factory()
    emp = _build_employer(session, name="Far Apart Co", state="NY")
    session.add(
        LcaFiling(
            case_number="LCA-FAR",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=150_000,
            worksite_city="New York",
            worksite_state="NY",
            received_date=date(2026, 1, 1),
            fiscal_year=2026,
        )
    )
    session.add(
        LayoffEvent(
            employer_id=emp.id,
            source="WARN_STATE_NY",
            effective_date=date(2026, 6, 1),  # >90 days after LCA
            workers_affected=75,
            location_city="New York",
            location_state="NY",
            reason="Warehouse consolidation",
        )
    )
    session.commit()

    score_all([emp.id])

    types = {
        f.flag_type
        for f in session_factory()
        .execute(select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id))
        .scalars()
        .all()
    }
    assert "LAYOFF_WITH_CONCURRENT_H1B" not in types
    assert "LAYOFF_SAME_WORKSITE_H1B" not in types
    assert "LAYOFF_SAME_SOC_H1B" not in types


def test_layoff_base_flag_but_different_worksite_does_not_escalate(session_factory):
    session = session_factory()
    emp = _build_employer(session, name="Geo Mismatch Inc", state="WA")
    session.add(
        LcaFiling(
            case_number="LCA-GEO",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="41-2011",  # sales — not the "software" hint
            wage_annualized=80_000,
            worksite_city="Bellevue",
            worksite_state="WA",
            received_date=date(2026, 2, 1),
            fiscal_year=2026,
        )
    )
    session.add(
        LayoffEvent(
            employer_id=emp.id,
            source="WARN_STATE_WA",
            effective_date=date(2026, 3, 15),  # 42 days apart — inside window
            workers_affected=50,
            location_city="Spokane",
            location_state="WA",
            reason="Warehouse closure",
        )
    )
    session.commit()
    score_all([emp.id])
    types = {
        f.flag_type
        for f in session_factory()
        .execute(select(AnomalyFlag).where(AnomalyFlag.employer_id == emp.id))
        .scalars()
        .all()
    }
    assert "LAYOFF_WITH_CONCURRENT_H1B" in types
    assert "LAYOFF_SAME_WORKSITE_H1B" not in types
    assert "LAYOFF_SAME_SOC_H1B" not in types


def test_tip_text_includes_displacement_block(session_factory):
    session = session_factory()
    emp = _build_employer(session, name="Displacement Co", state="TX")
    session.add(
        LcaFiling(
            case_number="LCA-DIS",
            employer_id=emp.id,
            naics_code="541512",
            soc_code="15-1252",
            wage_annualized=150_000,
            worksite_city="Austin",
            worksite_state="TX",
            received_date=date(2026, 3, 1),
            fiscal_year=2026,
        )
    )
    session.add(
        LayoffEvent(
            employer_id=emp.id,
            source="WARN_STATE_TX",
            notice_date=date(2026, 2, 1),
            effective_date=date(2026, 4, 1),
            workers_affected=120,
            location_city="Austin",
            location_state="TX",
            reason="Software engineering RIF",
            source_url="https://twc.texas.gov/warn/example",
        )
    )
    session.commit()
    score_all([emp.id])

    report = generate_report(emp.id)
    assert "LAYOFFS AND CONCURRENT H-1B FILINGS" in report
    assert "212(n)(1)(E)" in report
    assert "LCA-DIS" in report

    tip = tip_text(emp.id)
    assert "INA 212(n)(1)(E) DISPLACEMENT COMPLAINT" in tip
    assert "120" in tip  # workers affected
    assert "https://twc.texas.gov/warn/example" in tip
    assert "LCA-DIS" in tip
