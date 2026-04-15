"""End-to-end integration test: seed → score → graph → investigate.

Runs the four main backend pipelines against a seeded in-memory SQLite DB and
asserts the AutoResearch investigation connectors produce the full set of
expected keys.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    EntityRelationship,
    LcaFiling,
    SocWageBenchmark,
)
from h1b_engine.graph.builder import build_address_links
from h1b_engine.investigate.connectors import fetch_all
from h1b_engine.score.engine import score_all


EXPECTED_CONNECTOR_KEYS = {
    "anomaly_flags",
    "lca_history",
    "uscis_approvals",
    "enforcement",
    "wage_benchmark",
    "entity_graph",
    "address_verification",
    "opencorporates",
    "layoffs",
    "personnel",
}


def test_full_pipeline(session_factory):
    session = session_factory()

    # Two employers at the same residential address - shell company smell.
    for i, name in enumerate(("Sunrise Convenience LLC", "Galaxy Gas & Food LLC")):
        emp = Employer(
            name=name,
            name_normalized=name.upper().replace(" LLC", "").strip(),
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
        session.add(emp)
        session.flush()
        session.add(
            LcaFiling(
                case_number=f"I-200-CASE-{i}",
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
                worksite_city="Decatur",
                worksite_state="GA",
                received_date=date(2024, 1, 1),
                fiscal_year=2024,
            )
        )
    session.add(
        SocWageBenchmark(
            soc_code="15-1252",
            oews_year=2024,
            area_type="NATIONAL",
            median_annual_wage=127000,
        )
    )
    session.commit()
    first_id = session.execute(
        select(Employer.id).where(Employer.name_normalized == "SUNRISE CONVENIENCE")
    ).scalar_one()

    # 1. Score every employer
    score_all()

    # 2. Build entity graph (address-based link)
    added = build_address_links()
    assert added >= 1

    # Confirm a relationship was persisted
    rels = session.execute(select(EntityRelationship)).scalars().all()
    assert len(rels) >= 1

    # Confirm at least one high-severity flag on the first employer
    flags = session.execute(
        select(AnomalyFlag).where(AnomalyFlag.employer_id == first_id)
    ).scalars().all()
    flag_types = {f.flag_type for f in flags}
    assert "NAICS_SOC_MISMATCH" in flag_types
    assert "RESIDENTIAL_ADDRESS" in flag_types

    # 3. Run the investigation connectors
    data = fetch_all(first_id)
    assert set(data.keys()) == EXPECTED_CONNECTOR_KEYS
    assert data["anomaly_flags"]["count"] >= 2
    assert data["lca_history"]["total"] == 1
    # Entity graph connector should see the neighbor at the shared address
    assert data["entity_graph"]["neighbor_count"] >= 1
    # Address verification connector should surface the other tenant
    assert data["address_verification"]["other_entities_at_address"] >= 1
