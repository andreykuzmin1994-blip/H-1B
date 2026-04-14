"""Layoff events table (WARN Act + supplemental sources).

Feeds the LAYOFF_WITH_CONCURRENT_H1B detector family, which surfaces employers
filing H-1B petitions inside the INA 212(n)(1)(E) 90-day non-displacement
window around a layoff.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-14

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "layoff_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "employer_id",
            sa.Integer,
            sa.ForeignKey("employers.id", ondelete="SET NULL"),
        ),
        sa.Column("employer_name_raw", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("notice_date", sa.Date),
        sa.Column("effective_date", sa.Date),
        sa.Column("workers_affected", sa.Integer),
        sa.Column("location_city", sa.String(200)),
        sa.Column("location_state", sa.String(2)),
        sa.Column("location_zip", sa.String(10)),
        sa.Column("reason", sa.String(200)),
        sa.Column("industry", sa.String(200)),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("external_id", sa.String(200)),
        sa.Column("raw", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("source", "external_id", name="uq_layoff_source_extid"),
    )
    op.create_index("idx_layoff_employer", "layoff_events", ["employer_id"])
    op.create_index("idx_layoff_effective_date", "layoff_events", ["effective_date"])
    op.create_index(
        "idx_layoff_location", "layoff_events", ["location_state", "location_city"]
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE layoff_events ALTER COLUMN raw TYPE JSONB "
            "USING raw::text::jsonb"
        )


def downgrade() -> None:
    op.drop_index("idx_layoff_location", table_name="layoff_events")
    op.drop_index("idx_layoff_effective_date", table_name="layoff_events")
    op.drop_index("idx_layoff_employer", table_name="layoff_events")
    op.drop_table("layoff_events")
