"""Investigation connectors.

Each connector pulls all relevant context for a single employer from one source
and returns a structured dict. The investigation report assembler stitches
those dicts together into a narrative.
"""
from __future__ import annotations

import abc
from collections import Counter
from typing import Any

from sqlalchemy import func, select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    EntityRelationship,
    LayoffEvent,
    LcaFiling,
    SocWageBenchmark,
    SosEntity,
    UscisEmployerStats,
    Violation,
)
from h1b_engine.graph.builder import subgraph_for_employer


class InvestigationConnector(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def fetch(self, employer_id: int) -> dict[str, Any]:
        """Fetch data for this employer. Must always return a dict."""


class LCAHistoryConnector(InvestigationConnector):
    name = "lca_history"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            filings = session.execute(
                select(LcaFiling).where(LcaFiling.employer_id == employer_id)
            ).scalars().all()
            if not filings:
                return {"total": 0, "filings": []}
            statuses = Counter(f.case_status for f in filings)
            socs = Counter(f.soc_code for f in filings if f.soc_code)
            wages = [float(f.wage_annualized) for f in filings if f.wage_annualized]
            secondary = Counter(f.secondary_entity for f in filings if f.secondary_entity)
            worksites = Counter(
                f"{f.worksite_city}, {f.worksite_state}" for f in filings if f.worksite_city
            )
            return {
                "total": len(filings),
                "statuses": dict(statuses),
                "soc_codes": socs.most_common(),
                "wage_min": min(wages) if wages else None,
                "wage_max": max(wages) if wages else None,
                "secondary_entities": secondary.most_common(5),
                "top_worksites": worksites.most_common(5),
                "fiscal_years": sorted({f.fiscal_year for f in filings if f.fiscal_year}),
            }


class USCISApprovalConnector(InvestigationConnector):
    name = "uscis_approvals"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            rows = session.execute(
                select(UscisEmployerStats).where(
                    UscisEmployerStats.employer_id == employer_id
                )
            ).scalars().all()
        if not rows:
            return {"available": False}
        initial_a = sum(r.initial_approvals for r in rows)
        initial_d = sum(r.initial_denials for r in rows)
        cont_a = sum(r.continuing_approvals for r in rows)
        cont_d = sum(r.continuing_denials for r in rows)
        total = initial_a + initial_d
        denial_rate = initial_d / total if total else 0.0
        return {
            "available": True,
            "initial_approvals": initial_a,
            "initial_denials": initial_d,
            "continuing_approvals": cont_a,
            "continuing_denials": cont_d,
            "initial_denial_rate": round(denial_rate, 4),
            "by_year": [
                {
                    "fiscal_year": r.fiscal_year,
                    "initial_approvals": r.initial_approvals,
                    "initial_denials": r.initial_denials,
                }
                for r in rows
            ],
        }


class EnforcementConnector(InvestigationConnector):
    name = "enforcement"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            violations = session.execute(
                select(Violation).where(Violation.employer_id == employer_id)
            ).scalars().all()
        return {
            "count": len(violations),
            "violations": [
                {
                    "source": v.source,
                    "type": v.violation_type,
                    "date": v.violation_date.isoformat() if v.violation_date else None,
                    "debarment_start": v.debarment_start.isoformat() if v.debarment_start else None,
                    "debarment_end": v.debarment_end.isoformat() if v.debarment_end else None,
                    "back_wages": float(v.back_wages_amount) if v.back_wages_amount else None,
                    "penalty": float(v.penalty_amount) if v.penalty_amount else None,
                    "description": v.description,
                }
                for v in violations
            ],
        }


class WageBenchmarkConnector(InvestigationConnector):
    name = "wage_benchmark"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            # Top SOCs filed by this employer
            top_socs = session.execute(
                select(LcaFiling.soc_code, func.count())
                .where(LcaFiling.employer_id == employer_id)
                .where(LcaFiling.soc_code.is_not(None))
                .group_by(LcaFiling.soc_code)
                .order_by(func.count().desc())
                .limit(3)
            ).all()
            results = []
            for soc_code, _ in top_socs:
                median_wage = session.execute(
                    select(
                        SocWageBenchmark.median_annual_wage,
                        SocWageBenchmark.soc_title,
                    )
                    .where(
                        SocWageBenchmark.soc_code == soc_code,
                        SocWageBenchmark.area_type == "NATIONAL",
                    )
                    .order_by(SocWageBenchmark.oews_year.desc())
                    .limit(1)
                ).first()
                employer_wages = session.execute(
                    select(func.avg(LcaFiling.wage_annualized)).where(
                        LcaFiling.employer_id == employer_id,
                        LcaFiling.soc_code == soc_code,
                    )
                ).scalar()
                pct_below = None
                if median_wage and median_wage[0] and employer_wages:
                    pct_below = round(
                        100 * (1 - float(employer_wages) / float(median_wage[0])), 1
                    )
                results.append(
                    {
                        "soc_code": soc_code,
                        "soc_title": median_wage[1] if median_wage else None,
                        "employer_avg_wage": float(employer_wages) if employer_wages else None,
                        "national_median": float(median_wage[0]) if median_wage and median_wage[0] else None,
                        "pct_below_median": pct_below,
                    }
                )
        return {"comparisons": results}


class EntityGraphConnector(InvestigationConnector):
    name = "entity_graph"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        graph = subgraph_for_employer(employer_id, max_depth=2)
        neighbors = [n for n in graph["nodes"] if n["id"] != employer_id]
        violators_connected = [n for n in neighbors if n["is_violator"]]
        return {
            "subgraph": graph,
            "neighbor_count": len(neighbors),
            "connected_violators": violators_connected,
        }


class AddressVerificationConnector(InvestigationConnector):
    name = "address_verification"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            emp = session.get(Employer, employer_id)
            if not emp:
                return {}
            other_at_addr = session.execute(
                select(func.count())
                .select_from(Employer)
                .where(
                    Employer.address_line1 == emp.address_line1,
                    Employer.city == emp.city,
                    Employer.state == emp.state,
                    Employer.id != emp.id,
                )
            ).scalar_one()
            return {
                "address_type": emp.address_type or "UNKNOWN",
                "address": " ".join(
                    [p for p in (emp.address_line1, emp.city, emp.state, emp.zip) if p]
                ),
                "lat": float(emp.address_geocoded_lat) if emp.address_geocoded_lat else None,
                "lng": float(emp.address_geocoded_lng) if emp.address_geocoded_lng else None,
                "other_entities_at_address": int(other_at_addr),
                "visadata_url": (
                    f"https://fraudreporter.visadata.org/?q={emp.address_line1}"
                    if emp.address_line1
                    else None
                ),
            }


class OpenCorporatesConnector(InvestigationConnector):
    name = "opencorporates"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            entity = session.execute(
                select(SosEntity).where(SosEntity.employer_id == employer_id)
            ).scalar_one_or_none()
        if not entity:
            return {"available": False}
        return {
            "available": True,
            "entity_name": entity.entity_name,
            "entity_type": entity.entity_type,
            "formation_date": entity.formation_date.isoformat() if entity.formation_date else None,
            "status": entity.status,
            "registered_agent": entity.registered_agent,
            "officers": entity.officers,
            "source_url": entity.source_url,
        }


class PublicWebPresenceConnector(InvestigationConnector):
    """Stub for website / LinkedIn / BBB / Google Maps presence.

    Phase 2 connector per spec. Returns a sentinel until implemented.
    """

    name = "public_web_presence"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        return {"available": False, "reason": "not_implemented"}


class LayoffConnector(InvestigationConnector):
    """Fetch WARN / layoffs.fyi notices and summarize H-1B concurrency.

    The report and tip generator use this to populate the INA 212(n)(1)(E)
    displacement narrative: total workers laid off, notice dates, and the set
    of LCAs filed inside the 90-day window.
    """

    name = "layoffs"
    WINDOW_DAYS = 90

    def fetch(self, employer_id: int) -> dict[str, Any]:
        from datetime import timedelta

        with get_session() as session:
            events = session.execute(
                select(LayoffEvent).where(LayoffEvent.employer_id == employer_id)
            ).scalars().all()
            if not events:
                return {"count": 0, "events": [], "concurrent_filings": []}

            filings = session.execute(
                select(LcaFiling).where(LcaFiling.employer_id == employer_id)
            ).scalars().all()

            concurrent: list[dict[str, Any]] = []
            window = timedelta(days=self.WINDOW_DAYS)
            for event in events:
                pivot = event.effective_date or event.notice_date
                if not pivot:
                    continue
                for f in filings:
                    if not f.received_date:
                        continue
                    if abs((f.received_date - pivot).days) <= self.WINDOW_DAYS:
                        concurrent.append(
                            {
                                "layoff_event_id": event.id,
                                "layoff_date": pivot.isoformat(),
                                "lca_case_number": f.case_number,
                                "lca_received_date": f.received_date.isoformat(),
                                "soc_code": f.soc_code,
                                "worksite": (
                                    f"{f.worksite_city}, {f.worksite_state}"
                                    if f.worksite_city or f.worksite_state
                                    else None
                                ),
                                "days_between": abs(
                                    (f.received_date - pivot).days
                                ),
                            }
                        )

            total_workers = sum(
                int(e.workers_affected) for e in events if e.workers_affected
            )
            return {
                "count": len(events),
                "total_workers_affected": total_workers,
                "events": [
                    {
                        "source": e.source,
                        "notice_date": e.notice_date.isoformat() if e.notice_date else None,
                        "effective_date": e.effective_date.isoformat()
                        if e.effective_date
                        else None,
                        "workers_affected": e.workers_affected,
                        "location": ", ".join(
                            p for p in (e.location_city, e.location_state) if p
                        )
                        or None,
                        "reason": e.reason,
                        "industry": e.industry,
                        "source_url": e.source_url,
                    }
                    for e in events
                ],
                "concurrent_filings": concurrent,
            }


class AnomalyFlagConnector(InvestigationConnector):
    name = "anomaly_flags"

    def fetch(self, employer_id: int) -> dict[str, Any]:
        with get_session() as session:
            flags = session.execute(
                select(AnomalyFlag).where(AnomalyFlag.employer_id == employer_id)
            ).scalars().all()
            return {
                "count": len(flags),
                "flags": [
                    {
                        "type": f.flag_type,
                        "severity": f.flag_severity,
                        "score": float(f.flag_score),
                        "description": f.description,
                        "evidence": f.evidence,
                    }
                    for f in flags
                ],
            }


CONNECTORS: list[InvestigationConnector] = [
    AnomalyFlagConnector(),
    LCAHistoryConnector(),
    USCISApprovalConnector(),
    EnforcementConnector(),
    WageBenchmarkConnector(),
    EntityGraphConnector(),
    AddressVerificationConnector(),
    OpenCorporatesConnector(),
    LayoffConnector(),
]


def fetch_all(employer_id: int) -> dict[str, Any]:
    """Run every connector and return a combined dict keyed by connector name."""
    return {c.name: c.fetch(employer_id) for c in CONNECTORS}
