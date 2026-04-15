"""Additional fraud-detection tables + LCA attorney columns.

Feeds triggers:
- MULTI_REGISTRATION_SAME_BENEFICIARY (h1b_registrations)
- COMMON_AGENT_CLUSTER (uses existing sos_entities)
- OFFICER_PRIOR_VISA_INDICTMENT (known_fraud_defendants)
- NO_PAYROLL_FOR_H1B_VOLUME (employer_payroll_records)
- PREPARER_ON_EOIR_DISCIPLINE_LIST (disciplined_practitioners + attorney cols on lca_filings)
- DOL_BENCHING_COMPLAINT_HISTORY (detector-only, uses existing violations)

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-15

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- lca_filings: attorney of record ------------------------------------
    op.add_column("lca_filings", sa.Column("attorney_name", sa.String(500)))
    op.add_column(
        "lca_filings", sa.Column("attorney_name_normalized", sa.String(500))
    )
    op.add_column("lca_filings", sa.Column("attorney_firm", sa.String(500)))
    op.create_index(
        "idx_lca_attorney_name_norm",
        "lca_filings",
        ["attorney_name_normalized"],
    )

    # --- h1b_registrations --------------------------------------------------
    op.create_table(
        "h1b_registrations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "employer_id",
            sa.Integer,
            sa.ForeignKey("employers.id", ondelete="SET NULL"),
        ),
        sa.Column("employer_name_raw", sa.String(500)),
        sa.Column("cap_fiscal_year", sa.Integer, nullable=False),
        sa.Column("beneficiary_full_name", sa.String(500), nullable=False),
        sa.Column("beneficiary_name_normalized", sa.String(500), nullable=False),
        sa.Column("beneficiary_date_of_birth", sa.Date),
        sa.Column("passport_last4", sa.String(4)),
        sa.Column("passport_country", sa.String(100)),
        sa.Column("status", sa.String(30)),
        sa.Column("source", sa.String(50), server_default="USCIS_REGISTRATION"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_reg_employer", "h1b_registrations", ["employer_id"])
    op.create_index(
        "idx_reg_cap_year", "h1b_registrations", ["cap_fiscal_year"]
    )
    op.create_index(
        "idx_reg_beneficiary_norm",
        "h1b_registrations",
        ["beneficiary_name_normalized"],
    )
    op.create_index(
        "idx_reg_beneficiary_year",
        "h1b_registrations",
        [
            "beneficiary_name_normalized",
            "beneficiary_date_of_birth",
            "cap_fiscal_year",
        ],
    )
    op.create_index(
        "idx_reg_passport_year",
        "h1b_registrations",
        ["passport_country", "passport_last4", "cap_fiscal_year"],
    )

    # --- known_fraud_defendants --------------------------------------------
    op.create_table(
        "known_fraud_defendants",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("role", sa.String(50)),
        sa.Column("case_id", sa.String(200)),
        sa.Column("case_title", sa.String(500)),
        sa.Column("case_date", sa.Date),
        sa.Column("agency", sa.String(50)),
        sa.Column("jurisdiction", sa.String(100)),
        sa.Column("offense_category", sa.String(100)),
        sa.Column("source", sa.String(50), server_default="DOJ_PRESS_RELEASE"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_fraud_defendant_name_norm",
        "known_fraud_defendants",
        ["name_normalized"],
    )

    # --- disciplined_practitioners -----------------------------------------
    op.create_table(
        "disciplined_practitioners",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("bar_id", sa.String(50)),
        sa.Column("jurisdiction", sa.String(100)),
        sa.Column("discipline_type", sa.String(100)),
        sa.Column("effective_date", sa.Date),
        sa.Column("reinstatement_date", sa.Date),
        sa.Column("source", sa.String(50), server_default="EOIR"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_disciplined_name_norm",
        "disciplined_practitioners",
        ["name_normalized"],
    )

    # --- employer_payroll_records ------------------------------------------
    op.create_table(
        "employer_payroll_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "employer_id",
            sa.Integer,
            sa.ForeignKey("employers.id", ondelete="CASCADE"),
        ),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("worker_count", sa.Integer),
        sa.Column("total_wages", sa.Numeric(14, 2)),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "employer_id",
            "fiscal_year",
            "source",
            name="uq_payroll_emp_year_source",
        ),
    )
    op.create_index(
        "idx_payroll_employer",
        "employer_payroll_records",
        ["employer_id"],
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table, col in (
            ("h1b_registrations", "raw"),
            ("disciplined_practitioners", "raw"),
            ("employer_payroll_records", "raw"),
        ):
            op.execute(
                f"ALTER TABLE {table} ALTER COLUMN {col} TYPE JSONB "
                f"USING {col}::text::jsonb"
            )


def downgrade() -> None:
    op.drop_index("idx_payroll_employer", table_name="employer_payroll_records")
    op.drop_table("employer_payroll_records")

    op.drop_index(
        "idx_disciplined_name_norm", table_name="disciplined_practitioners"
    )
    op.drop_table("disciplined_practitioners")

    op.drop_index(
        "idx_fraud_defendant_name_norm", table_name="known_fraud_defendants"
    )
    op.drop_table("known_fraud_defendants")

    op.drop_index("idx_reg_passport_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_beneficiary_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_beneficiary_norm", table_name="h1b_registrations")
    op.drop_index("idx_reg_cap_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_employer", table_name="h1b_registrations")
    op.drop_table("h1b_registrations")

    op.drop_index("idx_lca_attorney_name_norm", table_name="lca_filings")
    op.drop_column("lca_filings", "attorney_firm")
    op.drop_column("lca_filings", "attorney_name_normalized")
    op.drop_column("lca_filings", "attorney_name")
