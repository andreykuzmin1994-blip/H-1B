"""Drop dead personnel/credentials + LCA attorney stubs.

Removes schema created by 0004 (in full) and parts of 0005 (h1b_registrations,
employer_payroll_records, disciplined_practitioners, and lca_filings attorney
columns). Keeps known_fraud_defendants since its detector
(OFFICER_PRIOR_VISA_INDICTMENT) remains in production.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 0005 fragments ---------------------------------------------------
    op.drop_index("idx_payroll_employer", table_name="employer_payroll_records")
    op.drop_table("employer_payroll_records")

    op.drop_index("idx_reg_passport_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_beneficiary_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_beneficiary_norm", table_name="h1b_registrations")
    op.drop_index("idx_reg_cap_year", table_name="h1b_registrations")
    op.drop_index("idx_reg_employer", table_name="h1b_registrations")
    op.drop_table("h1b_registrations")

    op.drop_index("idx_disciplined_name_norm", table_name="disciplined_practitioners")
    op.drop_table("disciplined_practitioners")

    op.drop_index("idx_lca_attorney_name_norm", table_name="lca_filings")
    op.drop_column("lca_filings", "attorney_firm")
    op.drop_column("lca_filings", "attorney_name_normalized")
    op.drop_column("lca_filings", "attorney_name")

    # --- 0004 (full personnel/credentials stack, FK-safe order) -----------
    op.drop_index("idx_credflag_type", table_name="credential_flags")
    op.drop_index("idx_credflag_employer", table_name="credential_flags")
    op.drop_index("idx_credflag_beneficiary", table_name="credential_flags")
    op.drop_table("credential_flags")

    op.drop_index("idx_claim_beneficiary", table_name="credential_claims")
    op.drop_table("credential_claims")

    op.drop_index("idx_beneficiary_passport", table_name="beneficiaries")
    op.drop_index("idx_beneficiary_name_dob", table_name="beneficiaries")
    op.drop_index("idx_beneficiary_name_norm", table_name="beneficiaries")
    op.drop_index("idx_beneficiary_employer", table_name="beneficiaries")
    op.drop_table("beneficiaries")

    op.drop_index("idx_evaluator_name_norm", table_name="credential_evaluators")
    op.drop_table("credential_evaluators")

    op.drop_index("idx_signatory_university", table_name="university_signatories")
    op.drop_index("idx_signatory_name_norm", table_name="university_signatories")
    op.drop_table("university_signatories")

    op.drop_index("idx_program_university", table_name="university_programs")
    op.drop_index("idx_program_name_norm", table_name="university_programs")
    op.drop_index("idx_program_lookup", table_name="university_programs")
    op.drop_table("university_programs")

    op.drop_index("idx_university_accreditation", table_name="universities")
    op.drop_index("idx_university_name_norm", table_name="universities")
    op.drop_table("universities")


def downgrade() -> None:
    # Recreate every dropped object faithfully (from 0004 + 0005).
    op.create_table(
        "universities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100)),
        sa.Column("city", sa.String(200)),
        sa.Column("ipeds_id", sa.String(20)),
        sa.Column("opeid", sa.String(20)),
        sa.Column("accreditor", sa.String(200)),
        sa.Column("accreditation_status", sa.String(20), server_default="UNKNOWN"),
        sa.Column("founded_year", sa.Integer),
        sa.Column("closed_year", sa.Integer),
        sa.Column("official_domain", sa.String(200)),
        sa.Column("source", sa.String(50), server_default="SEED"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("name_normalized", "country", name="uq_university_name_country"),
    )
    op.create_index("idx_university_name_norm", "universities", ["name_normalized"])
    op.create_index("idx_university_accreditation", "universities", ["accreditation_status"])

    op.create_table(
        "university_programs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "university_id",
            sa.Integer,
            sa.ForeignKey("universities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("degree_level", sa.String(20), nullable=False),
        sa.Column("cip_code", sa.String(10)),
        sa.Column("program_name", sa.String(500), nullable=False),
        sa.Column("program_name_normalized", sa.String(500), nullable=False),
        sa.Column("first_conferred_year", sa.Integer),
        sa.Column("last_conferred_year", sa.Integer),
        sa.Column("source", sa.String(50), server_default="IPEDS"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_program_lookup",
        "university_programs",
        ["university_id", "degree_level", "program_name_normalized"],
    )
    op.create_index("idx_program_name_norm", "university_programs", ["program_name_normalized"])
    op.create_index("idx_program_university", "university_programs", ["university_id"])

    op.create_table(
        "university_signatories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "university_id",
            sa.Integer,
            sa.ForeignKey("universities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("department", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("active_from", sa.Date),
        sa.Column("active_until", sa.Date),
        sa.Column("is_deceased", sa.Integer, server_default="0"),
        sa.Column("source", sa.String(50), server_default="UNIVERSITY_DIRECTORY"),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_signatory_name_norm", "university_signatories", ["name_normalized"])
    op.create_index("idx_signatory_university", "university_signatories", ["university_id"])

    op.create_table(
        "credential_evaluators",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("country", sa.String(100)),
        sa.Column("naces_member", sa.Integer, server_default="0"),
        sa.Column("aice_member", sa.Integer, server_default="0"),
        sa.Column("website", sa.String(500)),
        sa.Column("notes", sa.Text),
        sa.Column("source", sa.String(50), server_default="SEED"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_evaluator_name_norm", "credential_evaluators", ["name_normalized"])

    op.create_table(
        "beneficiaries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "employer_id",
            sa.Integer,
            sa.ForeignKey("employers.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "lca_filing_id",
            sa.Integer,
            sa.ForeignKey("lca_filings.id", ondelete="SET NULL"),
        ),
        sa.Column("full_name", sa.String(500), nullable=False),
        sa.Column("name_normalized", sa.String(500), nullable=False),
        sa.Column("date_of_birth", sa.Date),
        sa.Column("country_of_birth", sa.String(100)),
        sa.Column("country_of_citizenship", sa.String(100)),
        sa.Column("passport_last4", sa.String(4)),
        sa.Column("passport_country", sa.String(100)),
        sa.Column("job_title_claimed", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_beneficiary_employer", "beneficiaries", ["employer_id"])
    op.create_index("idx_beneficiary_name_norm", "beneficiaries", ["name_normalized"])
    op.create_index(
        "idx_beneficiary_name_dob", "beneficiaries", ["name_normalized", "date_of_birth"]
    )
    op.create_index(
        "idx_beneficiary_passport", "beneficiaries", ["passport_country", "passport_last4"]
    )

    op.create_table(
        "credential_claims",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "beneficiary_id",
            sa.Integer,
            sa.ForeignKey("beneficiaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("claim_type", sa.String(20), nullable=False),
        sa.Column("university_name_raw", sa.String(500)),
        sa.Column(
            "university_id",
            sa.Integer,
            sa.ForeignKey("universities.id", ondelete="SET NULL"),
        ),
        sa.Column("degree_level", sa.String(20)),
        sa.Column("degree_title", sa.String(500)),
        sa.Column("field_of_study", sa.String(500)),
        sa.Column("country", sa.String(100)),
        sa.Column("enrollment_start_date", sa.Date),
        sa.Column("graduation_date", sa.Date),
        sa.Column("signatory_name_raw", sa.String(500)),
        sa.Column("signatory_title_raw", sa.String(200)),
        sa.Column("signatory_email_raw", sa.String(320)),
        sa.Column("evaluator_name_raw", sa.String(500)),
        sa.Column("evaluator_organization_raw", sa.String(500)),
        sa.Column("evidence_url", sa.String(1000)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_claim_beneficiary", "credential_claims", ["beneficiary_id"])

    op.create_table(
        "credential_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "beneficiary_id",
            sa.Integer,
            sa.ForeignKey("beneficiaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "credential_claim_id",
            sa.Integer,
            sa.ForeignKey("credential_claims.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "employer_id",
            sa.Integer,
            sa.ForeignKey("employers.id", ondelete="SET NULL"),
        ),
        sa.Column("flag_type", sa.String(60), nullable=False),
        sa.Column("flag_severity", sa.String(10)),
        sa.Column("flag_score", sa.Numeric(5, 2), server_default="0"),
        sa.Column("description", sa.Text),
        sa.Column("evidence", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_credflag_beneficiary", "credential_flags", ["beneficiary_id"])
    op.create_index("idx_credflag_employer", "credential_flags", ["employer_id"])
    op.create_index("idx_credflag_type", "credential_flags", ["flag_type"])

    # --- lca_filings attorney columns -------------------------------------
    op.add_column("lca_filings", sa.Column("attorney_name", sa.String(500)))
    op.add_column("lca_filings", sa.Column("attorney_name_normalized", sa.String(500)))
    op.add_column("lca_filings", sa.Column("attorney_firm", sa.String(500)))
    op.create_index(
        "idx_lca_attorney_name_norm", "lca_filings", ["attorney_name_normalized"]
    )

    # --- disciplined_practitioners ----------------------------------------
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
        "idx_disciplined_name_norm", "disciplined_practitioners", ["name_normalized"]
    )

    # --- h1b_registrations ------------------------------------------------
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
    op.create_index("idx_reg_cap_year", "h1b_registrations", ["cap_fiscal_year"])
    op.create_index(
        "idx_reg_beneficiary_norm", "h1b_registrations", ["beneficiary_name_normalized"]
    )
    op.create_index(
        "idx_reg_beneficiary_year",
        "h1b_registrations",
        ["beneficiary_name_normalized", "beneficiary_date_of_birth", "cap_fiscal_year"],
    )
    op.create_index(
        "idx_reg_passport_year",
        "h1b_registrations",
        ["passport_country", "passport_last4", "cap_fiscal_year"],
    )

    # --- employer_payroll_records -----------------------------------------
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
            "employer_id", "fiscal_year", "source", name="uq_payroll_emp_year_source"
        ),
    )
    op.create_index("idx_payroll_employer", "employer_payroll_records", ["employer_id"])
