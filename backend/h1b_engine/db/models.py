"""SQLAlchemy ORM models matching the schema in the project spec."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from h1b_engine.db.base import Base


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ein: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    address_line1: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))
    naics_code: Mapped[str | None] = mapped_column(String(6), index=True)
    industry_description: Mapped[str | None] = mapped_column(String(500))
    address_type: Mapped[str | None] = mapped_column(String(20))
    address_geocoded_lat: Mapped[float | None] = mapped_column(Numeric(10, 7))
    address_geocoded_lng: Mapped[float | None] = mapped_column(Numeric(10, 7))
    first_filing_date: Mapped[date | None] = mapped_column(Date)
    last_filing_date: Mapped[date | None] = mapped_column(Date)
    total_lca_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    filings: Mapped[list["LcaFiling"]] = relationship(back_populates="employer")
    violations: Mapped[list["Violation"]] = relationship(back_populates="employer")
    flags: Mapped[list["AnomalyFlag"]] = relationship(back_populates="employer")
    layoff_events: Mapped[list["LayoffEvent"]] = relationship(back_populates="employer")

    __table_args__ = (
        Index("idx_employers_address", "address_line1", "city", "state"),
        Index("idx_employers_anomaly", "anomaly_score"),
        UniqueConstraint("name_normalized", "state", name="uq_employer_name_state"),
    )


class LcaFiling(Base):
    __tablename__ = "lca_filings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    case_status: Mapped[str | None] = mapped_column(String(20), index=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), index=True
    )
    employer_name_raw: Mapped[str | None] = mapped_column(String(500))
    naics_code: Mapped[str | None] = mapped_column(String(6))
    soc_code: Mapped[str | None] = mapped_column(String(10), index=True)
    soc_title: Mapped[str | None] = mapped_column(String(500))
    job_title: Mapped[str | None] = mapped_column(String(500))
    wage_from: Mapped[float | None] = mapped_column(Numeric(12, 2))
    wage_unit: Mapped[str | None] = mapped_column(String(20))
    wage_annualized: Mapped[float | None] = mapped_column(Numeric(12, 2))
    prevailing_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pw_unit: Mapped[str | None] = mapped_column(String(20))
    pw_annualized: Mapped[float | None] = mapped_column(Numeric(12, 2))
    wage_ratio: Mapped[float | None] = mapped_column(Numeric(5, 3))
    worksite_city: Mapped[str | None] = mapped_column(String(200))
    worksite_state: Mapped[str | None] = mapped_column(String(2))
    worksite_zip: Mapped[str | None] = mapped_column(String(10))
    secondary_entity: Mapped[str | None] = mapped_column(String(500))
    total_workers: Mapped[int | None] = mapped_column(Integer)
    visa_class: Mapped[str | None] = mapped_column(String(10))
    received_date: Mapped[date | None] = mapped_column(Date)
    decision_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    employer: Mapped[Employer | None] = relationship(back_populates="filings")


class UscisEmployerStats(Base):
    """USCIS H-1B Employer Data Hub stats (approval/denial rates)."""

    __tablename__ = "uscis_employer_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), index=True
    )
    employer_name_raw: Mapped[str | None] = mapped_column(String(500))
    tax_id_last4: Mapped[str | None] = mapped_column(String(4))
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    initial_approvals: Mapped[int] = mapped_column(Integer, default=0)
    initial_denials: Mapped[int] = mapped_column(Integer, default=0)
    continuing_approvals: Mapped[int] = mapped_column(Integer, default=0)
    continuing_denials: Mapped[int] = mapped_column(Integer, default=0)
    city: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str | None] = mapped_column(String(2))
    zip: Mapped[str | None] = mapped_column(String(10))
    naics_code: Mapped[str | None] = mapped_column(String(6))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Violation(Base):
    __tablename__ = "violations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), index=True
    )
    employer_name_raw: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(50))  # DOL_WILLFUL, WHD_ENFORCEMENT, USCIS_DEBARMENT
    violation_type: Mapped[str | None] = mapped_column(String(200))
    violation_date: Mapped[date | None] = mapped_column(Date)
    debarment_start: Mapped[date | None] = mapped_column(Date)
    debarment_end: Mapped[date | None] = mapped_column(Date)
    back_wages_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    penalty_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    employer: Mapped[Employer | None] = relationship(back_populates="violations")


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="CASCADE"), index=True
    )
    lca_filing_id: Mapped[int | None] = mapped_column(
        ForeignKey("lca_filings.id", ondelete="CASCADE")
    )
    flag_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    flag_severity: Mapped[str | None] = mapped_column(String(10))  # CRITICAL|HIGH|MEDIUM|LOW
    flag_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    description: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    employer: Mapped[Employer | None] = relationship(back_populates="flags")


class EntityRelationship(Base):
    __tablename__ = "entity_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id_a: Mapped[int] = mapped_column(
        ForeignKey("employers.id", ondelete="CASCADE"), index=True
    )
    employer_id_b: Mapped[int] = mapped_column(
        ForeignKey("employers.id", ondelete="CASCADE"), index=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50)
    )  # SHARED_ADDRESS|SHARED_AGENT|SHARED_OFFICER|NAME_VARIANT
    confidence: Mapped[float] = mapped_column(Numeric(3, 2), default=1.0)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "employer_id_a",
            "employer_id_b",
            "relationship_type",
            name="uq_entity_rel",
        ),
    )


class SosEntity(Base):
    __tablename__ = "sos_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), index=True
    )
    state: Mapped[str | None] = mapped_column(String(2))
    entity_name: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    formation_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(50))
    registered_agent: Mapped[str | None] = mapped_column(String(500))
    principal_address: Mapped[str | None] = mapped_column(String(500))
    officers: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SocWageBenchmark(Base):
    __tablename__ = "soc_wage_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    soc_code: Mapped[str] = mapped_column(String(10), nullable=False)
    soc_title: Mapped[str | None] = mapped_column(String(500))
    oews_year: Mapped[int] = mapped_column(Integer, nullable=False)
    area_type: Mapped[str] = mapped_column(String(20), nullable=False)  # NATIONAL|STATE|MSA
    area_code: Mapped[str | None] = mapped_column(String(10))
    area_name: Mapped[str | None] = mapped_column(String(200))
    employment: Mapped[int | None] = mapped_column(Integer)
    mean_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    median_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pct10_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pct25_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pct75_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    pct90_annual_wage: Mapped[float | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "soc_code",
            "oews_year",
            "area_type",
            "area_code",
            name="uq_soc_wage_benchmark",
        ),
        Index("idx_soc_wage_lookup", "soc_code", "oews_year", "area_type"),
    )


class LayoffEvent(Base):
    """Layoff notices linked to an employer.

    Sourced from federal / state WARN Act filings (the only authoritative public
    record of US mass layoffs, required at 60 days' notice for layoffs >= 50
    workers) plus optional supplemental feeds such as layoffs.fyi for layoffs
    that fall under WARN thresholds.

    This is the substrate for the LAYOFF_WITH_CONCURRENT_H1B detector, which
    checks the INA section 212(n)(1)(E) 90-day non-displacement window.
    """

    __tablename__ = "layoff_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employer_id: Mapped[int | None] = mapped_column(
        ForeignKey("employers.id", ondelete="SET NULL"), index=True
    )
    employer_name_raw: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # WARN_FEDERAL|WARN_STATE_{XX}|LAYOFFS_FYI|NEWS
    notice_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date, index=True)
    workers_affected: Mapped[int | None] = mapped_column(Integer)
    location_city: Mapped[str | None] = mapped_column(String(200))
    location_state: Mapped[str | None] = mapped_column(String(2))
    location_zip: Mapped[str | None] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(200))
    industry: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    external_id: Mapped[str | None] = mapped_column(String(200))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    employer: Mapped[Employer | None] = relationship(back_populates="layoff_events")

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_layoff_source_extid"),
        Index("idx_layoff_effective_date", "effective_date"),
        Index("idx_layoff_location", "location_state", "location_city"),
    )


class IngestionRun(Base):
    """Tracks every ingestion run so we can resume and audit."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|failed
    rows_in: Mapped[int] = mapped_column(Integer, default=0)
    rows_out: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class KnownFraudDefendant(Base):
    """Named individuals/entities from DOJ/ICE/USCIS visa-fraud actions.

    Populated from press-release NER. Referenced by the
    OFFICER_PRIOR_VISA_INDICTMENT detector against ``SosEntity.officers``.
    """

    __tablename__ = "known_fraud_defendants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    role: Mapped[str | None] = mapped_column(
        String(50)
    )  # DEFENDANT | CO_CONSPIRATOR | CORPORATE
    case_id: Mapped[str | None] = mapped_column(String(200))
    case_title: Mapped[str | None] = mapped_column(String(500))
    case_date: Mapped[date | None] = mapped_column(Date)
    agency: Mapped[str | None] = mapped_column(String(50))  # DOJ | ICE | USCIS | STATE_AG
    jurisdiction: Mapped[str | None] = mapped_column(String(100))
    offense_category: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(50), default="DOJ_PRESS_RELEASE")
    source_url: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
