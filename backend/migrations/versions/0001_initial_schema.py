"""Initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-14

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "employers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ein", sa.String(20)),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("address_line1", sa.String(500)),
        sa.Column("city", sa.String(200)),
        sa.Column("state", sa.String(2)),
        sa.Column("zip", sa.String(10)),
        sa.Column("naics_code", sa.String(6)),
        sa.Column("industry_description", sa.String(500)),
        sa.Column("address_type", sa.String(20)),
        sa.Column("address_geocoded_lat", sa.Numeric(10, 7)),
        sa.Column("address_geocoded_lng", sa.Numeric(10, 7)),
        sa.Column("first_filing_date", sa.Date),
        sa.Column("last_filing_date", sa.Date),
        sa.Column("total_lca_count", sa.Integer, server_default="0"),
        sa.Column("anomaly_score", sa.Numeric(5, 2), server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("name_normalized", "state", name="uq_employer_name_state"),
    )
    op.create_index("idx_employers_name_norm", "employers", ["name_normalized"])
    op.create_index("idx_employers_address", "employers", ["address_line1", "city", "state"])
    op.create_index("idx_employers_naics", "employers", ["naics_code"])
    op.create_index("idx_employers_anomaly", "employers", ["anomaly_score"])

    op.create_table(
        "lca_filings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_number", sa.String(50), unique=True, nullable=False),
        sa.Column("case_status", sa.String(20)),
        sa.Column("employer_id", sa.Integer, sa.ForeignKey("employers.id", ondelete="SET NULL")),
        sa.Column("employer_name_raw", sa.String(500)),
        sa.Column("naics_code", sa.String(6)),
        sa.Column("soc_code", sa.String(10)),
        sa.Column("soc_title", sa.String(500)),
        sa.Column("job_title", sa.String(500)),
        sa.Column("wage_from", sa.Numeric(12, 2)),
        sa.Column("wage_unit", sa.String(20)),
        sa.Column("wage_annualized", sa.Numeric(12, 2)),
        sa.Column("prevailing_wage", sa.Numeric(12, 2)),
        sa.Column("pw_unit", sa.String(20)),
        sa.Column("pw_annualized", sa.Numeric(12, 2)),
        sa.Column("wage_ratio", sa.Numeric(5, 3)),
        sa.Column("worksite_city", sa.String(200)),
        sa.Column("worksite_state", sa.String(2)),
        sa.Column("worksite_zip", sa.String(10)),
        sa.Column("secondary_entity", sa.String(500)),
        sa.Column("total_workers", sa.Integer),
        sa.Column("visa_class", sa.String(10)),
        sa.Column("received_date", sa.Date),
        sa.Column("decision_date", sa.Date),
        sa.Column("fiscal_year", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_lca_employer", "lca_filings", ["employer_id"])
    op.create_index("idx_lca_soc", "lca_filings", ["soc_code"])
    op.create_index("idx_lca_fiscal_year", "lca_filings", ["fiscal_year"])
    op.create_index("idx_lca_case_status", "lca_filings", ["case_status"])

    op.create_table(
        "uscis_employer_stats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id", sa.Integer, sa.ForeignKey("employers.id", ondelete="SET NULL")),
        sa.Column("employer_name_raw", sa.String(500)),
        sa.Column("tax_id_last4", sa.String(4)),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("initial_approvals", sa.Integer, server_default="0"),
        sa.Column("initial_denials", sa.Integer, server_default="0"),
        sa.Column("continuing_approvals", sa.Integer, server_default="0"),
        sa.Column("continuing_denials", sa.Integer, server_default="0"),
        sa.Column("city", sa.String(200)),
        sa.Column("state", sa.String(2)),
        sa.Column("zip", sa.String(10)),
        sa.Column("naics_code", sa.String(6)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_uscis_employer", "uscis_employer_stats", ["employer_id"])

    op.create_table(
        "violations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id", sa.Integer, sa.ForeignKey("employers.id", ondelete="SET NULL")),
        sa.Column("employer_name_raw", sa.String(500)),
        sa.Column("source", sa.String(50)),
        sa.Column("violation_type", sa.String(200)),
        sa.Column("violation_date", sa.Date),
        sa.Column("debarment_start", sa.Date),
        sa.Column("debarment_end", sa.Date),
        sa.Column("back_wages_amount", sa.Numeric(12, 2)),
        sa.Column("penalty_amount", sa.Numeric(12, 2)),
        sa.Column("description", sa.Text),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_violations_employer", "violations", ["employer_id"])

    op.create_table(
        "anomaly_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id", sa.Integer, sa.ForeignKey("employers.id", ondelete="CASCADE")),
        sa.Column("lca_filing_id", sa.Integer, sa.ForeignKey("lca_filings.id", ondelete="CASCADE")),
        sa.Column("flag_type", sa.String(50), nullable=False),
        sa.Column("flag_severity", sa.String(10)),
        sa.Column("flag_score", sa.Numeric(5, 2), server_default="0"),
        sa.Column("description", sa.Text),
        sa.Column("evidence", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_anomaly_employer", "anomaly_flags", ["employer_id"])
    op.create_index("idx_anomaly_type", "anomaly_flags", ["flag_type"])

    op.create_table(
        "entity_relationships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id_a", sa.Integer, sa.ForeignKey("employers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("employer_id_b", sa.Integer, sa.ForeignKey("employers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(50)),
        sa.Column("confidence", sa.Numeric(3, 2), server_default="1.0"),
        sa.Column("evidence", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "employer_id_a", "employer_id_b", "relationship_type", name="uq_entity_rel"
        ),
    )
    op.create_index("idx_entity_rel_a", "entity_relationships", ["employer_id_a"])
    op.create_index("idx_entity_rel_b", "entity_relationships", ["employer_id_b"])

    op.create_table(
        "sos_entities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employer_id", sa.Integer, sa.ForeignKey("employers.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(2)),
        sa.Column("entity_name", sa.String(500)),
        sa.Column("entity_type", sa.String(50)),
        sa.Column("formation_date", sa.Date),
        sa.Column("status", sa.String(50)),
        sa.Column("registered_agent", sa.String(500)),
        sa.Column("principal_address", sa.String(500)),
        sa.Column("officers", sa.JSON),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("fetched_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_sos_employer", "sos_entities", ["employer_id"])

    op.create_table(
        "soc_wage_benchmarks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("soc_code", sa.String(10), nullable=False),
        sa.Column("soc_title", sa.String(500)),
        sa.Column("oews_year", sa.Integer, nullable=False),
        sa.Column("area_type", sa.String(20), nullable=False),
        sa.Column("area_code", sa.String(10)),
        sa.Column("area_name", sa.String(200)),
        sa.Column("employment", sa.Integer),
        sa.Column("mean_annual_wage", sa.Numeric(12, 2)),
        sa.Column("median_annual_wage", sa.Numeric(12, 2)),
        sa.Column("pct10_annual_wage", sa.Numeric(12, 2)),
        sa.Column("pct25_annual_wage", sa.Numeric(12, 2)),
        sa.Column("pct75_annual_wage", sa.Numeric(12, 2)),
        sa.Column("pct90_annual_wage", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "soc_code", "oews_year", "area_type", "area_code", name="uq_soc_wage_benchmark"
        ),
    )
    op.create_index(
        "idx_soc_wage_lookup", "soc_wage_benchmarks", ["soc_code", "oews_year", "area_type"]
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("params", sa.JSON),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime),
        sa.Column("status", sa.String(20), server_default="running"),
        sa.Column("rows_in", sa.Integer, server_default="0"),
        sa.Column("rows_out", sa.Integer, server_default="0"),
        sa.Column("error", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("soc_wage_benchmarks")
    op.drop_table("sos_entities")
    op.drop_table("entity_relationships")
    op.drop_table("anomaly_flags")
    op.drop_table("violations")
    op.drop_table("uscis_employer_stats")
    op.drop_table("lca_filings")
    op.drop_table("employers")
