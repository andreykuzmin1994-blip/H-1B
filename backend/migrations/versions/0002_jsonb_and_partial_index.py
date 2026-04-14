"""JSONB conversion and partial index on non-zero anomaly scores.

Spec follow-up: JSONB buys us GIN indexing and @> containment queries on
evidence/officers/params payloads. Partial index keeps ``ORDER BY
anomaly_score DESC`` cheap on tables dominated by zero-scored employers.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-14

"""
from __future__ import annotations

from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


_JSON_COLUMNS = [
    ("anomaly_flags", "evidence"),
    ("entity_relationships", "evidence"),
    ("sos_entities", "officers"),
    ("ingestion_runs", "params"),
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table, column in _JSON_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSONB "
            f"USING {column}::text::jsonb"
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_employers_anomaly_nonzero "
        "ON employers (anomaly_score DESC) WHERE anomaly_score > 0"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_employers_anomaly_nonzero")
    for table, column in _JSON_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSON "
            f"USING {column}::text::json"
        )
