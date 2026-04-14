"""Individual anomaly detectors. Each returns a list of (FlagDefinition, evidence)."""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from h1b_engine.db.models import (
    AnomalyFlag,
    Employer,
    EntityRelationship,
    LcaFiling,
    SocWageBenchmark,
    SosEntity,
    UscisEmployerStats,
    Violation,
)
from h1b_engine.graph.builder import subgraph_for_employer
from h1b_engine.score.flags import (
    ANOMALY_FLAGS,
    BUSINESS_PARK_KEYWORDS,
    NAICS_SOC_HARD_RULES,
    NON_SPECIALTY_SOCS,
    RELATIONSHIP_WEIGHTS,
    STAFFING_NAICS,
    FlagDefinition,
)

log = logging.getLogger(__name__)

FlagOutput = tuple[FlagDefinition, dict[str, Any], int | None]  # (flag, evidence, lca_filing_id)


# --------------------------------------------------------------------------- #
# Helper aggregations that can be cached per scoring run
# --------------------------------------------------------------------------- #


def compute_naics_soc_frequency(session: Session) -> dict[str, dict[str, float]]:
    """Return per-NAICS distribution of SOC 2-digit major groups as fraction."""
    rows = session.execute(
        select(LcaFiling.naics_code, LcaFiling.soc_code, func.count())
        .where(LcaFiling.naics_code.is_not(None))
        .where(LcaFiling.soc_code.is_not(None))
        .group_by(LcaFiling.naics_code, LcaFiling.soc_code)
    ).all()
    counter: dict[str, Counter[str]] = defaultdict(Counter)
    for naics, soc, count in rows:
        if not naics or not soc:
            continue
        soc_major = soc.split("-")[0] if "-" in soc else soc[:2]
        counter[naics][soc_major] += count
    distribution: dict[str, dict[str, float]] = {}
    for naics, soc_counts in counter.items():
        total = sum(soc_counts.values())
        if total == 0:
            continue
        distribution[naics] = {soc: cnt / total for soc, cnt in soc_counts.items()}
    return distribution


def compute_address_clusters(session: Session, threshold: int = 5) -> set[str]:
    rows = session.execute(
        select(
            Employer.address_line1,
            Employer.city,
            Employer.state,
            Employer.zip,
            func.count(Employer.id),
        )
        .where(Employer.address_line1.is_not(None))
        .group_by(Employer.address_line1, Employer.city, Employer.state, Employer.zip)
    ).all()
    clusters = set()
    for a, c, s, z, n in rows:
        if n >= threshold:
            combined = f"{a or ''} {c or ''}".upper()
            if any(kw in combined for kw in BUSINESS_PARK_KEYWORDS):
                continue
            clusters.add(f"{a}|{c}|{s}|{z}")
    return clusters


def compute_national_soc_medians(session: Session) -> dict[str, float]:
    rows = session.execute(
        select(SocWageBenchmark.soc_code, func.max(SocWageBenchmark.median_annual_wage))
        .where(SocWageBenchmark.area_type == "NATIONAL")
        .group_by(SocWageBenchmark.soc_code)
    ).all()
    return {soc: float(med) for soc, med in rows if soc and med is not None}


def compute_soc_denial_rates(session: Session) -> dict[str, float]:
    """Average denial rate per SOC code, derived from joined USCIS + LCA rows."""
    # USCIS data is at employer/FY granularity. Using employer NAICS proxy.
    # Primary SOC per employer is the mode of their LCA filings.
    employer_primary_soc: dict[int, str] = {}
    soc_rows = session.execute(
        select(LcaFiling.employer_id, LcaFiling.soc_code, func.count())
        .where(LcaFiling.employer_id.is_not(None))
        .where(LcaFiling.soc_code.is_not(None))
        .group_by(LcaFiling.employer_id, LcaFiling.soc_code)
    ).all()
    tally: dict[int, Counter[str]] = defaultdict(Counter)
    for eid, soc, cnt in soc_rows:
        tally[eid][soc] += cnt
    for eid, counter in tally.items():
        employer_primary_soc[eid] = counter.most_common(1)[0][0]

    totals_by_soc: dict[str, list[tuple[int, int]]] = defaultdict(list)
    uscis_rows = session.execute(
        select(
            UscisEmployerStats.employer_id,
            func.sum(UscisEmployerStats.initial_approvals),
            func.sum(UscisEmployerStats.initial_denials),
        )
        .where(UscisEmployerStats.employer_id.is_not(None))
        .group_by(UscisEmployerStats.employer_id)
    ).all()
    for eid, approvals, denials in uscis_rows:
        soc = employer_primary_soc.get(eid)
        if not soc:
            continue
        totals_by_soc[soc].append((int(approvals or 0), int(denials or 0)))

    avg: dict[str, float] = {}
    for soc, entries in totals_by_soc.items():
        approvals = sum(a for a, _ in entries)
        denials = sum(d for _, d in entries)
        total = approvals + denials
        if total > 0:
            avg[soc] = denials / total
    return avg


def compute_violator_employer_ids(session: Session) -> set[int]:
    rows = session.execute(
        select(Violation.employer_id).where(Violation.employer_id.is_not(None))
    ).all()
    return {r[0] for r in rows if r[0] is not None}


# --------------------------------------------------------------------------- #
# Per-employer detector
# --------------------------------------------------------------------------- #


def detect_for_employer(
    session: Session,
    employer: Employer,
    *,
    naics_soc_freq: dict[str, dict[str, float]],
    address_clusters: set[str],
    soc_medians: dict[str, float],
    soc_denial_rates: dict[str, float],
    violator_ids: set[int],
) -> list[FlagOutput]:
    outputs: list[FlagOutput] = []
    filings = session.execute(
        select(LcaFiling).where(LcaFiling.employer_id == employer.id)
    ).scalars().all()

    # -- NAICS-SOC mismatch --------------------------------------------------
    naics = (employer.naics_code or "")[:3]
    for filing in filings:
        if not filing.soc_code or not filing.naics_code:
            continue
        soc_major = filing.soc_code.split("-")[0] if "-" in filing.soc_code else filing.soc_code[:2]

        hard_hit = any(
            filing.naics_code.startswith(pref) and soc_major.startswith(soc_pref)
            for pref, soc_pref in NAICS_SOC_HARD_RULES
        )
        dist = naics_soc_freq.get(filing.naics_code, {})
        freq = dist.get(soc_major, 0.0)
        if hard_hit or (dist and freq < 0.005):
            outputs.append(
                (
                    ANOMALY_FLAGS["NAICS_SOC_MISMATCH"],
                    {
                        "naics": filing.naics_code,
                        "soc_code": filing.soc_code,
                        "frequency": freq,
                        "hard_rule": hard_hit,
                    },
                    filing.id,
                )
            )
            break  # only flag once per employer for this type

    # -- NON_SPECIALTY_SOC ---------------------------------------------------
    for filing in filings:
        if filing.soc_code and filing.soc_code in NON_SPECIALTY_SOCS:
            outputs.append(
                (
                    ANOMALY_FLAGS["NON_SPECIALTY_SOC"],
                    {"soc_code": filing.soc_code, "soc_title": filing.soc_title},
                    filing.id,
                )
            )
            break

    # -- WAGE_FAR_BELOW_SOC_MEDIAN ------------------------------------------
    for filing in filings:
        if not filing.soc_code or not filing.wage_annualized:
            continue
        median = soc_medians.get(filing.soc_code)
        if not median:
            # try SOC major group fallback (many OEWS rollups use -0000)
            if "-" in filing.soc_code:
                major = filing.soc_code.split("-")[0] + "-0000"
                median = soc_medians.get(major)
        if median and float(filing.wage_annualized) < 0.5 * median:
            outputs.append(
                (
                    ANOMALY_FLAGS["WAGE_FAR_BELOW_SOC_MEDIAN"],
                    {
                        "wage_annualized": float(filing.wage_annualized),
                        "soc_median": median,
                        "soc_code": filing.soc_code,
                    },
                    filing.id,
                )
            )
            break

    # -- WAGE_BELOW_PREVAILING ----------------------------------------------
    for filing in filings:
        if filing.wage_annualized and filing.pw_annualized:
            if float(filing.wage_annualized) < float(filing.pw_annualized):
                outputs.append(
                    (
                        ANOMALY_FLAGS["WAGE_BELOW_PREVAILING"],
                        {
                            "wage_annualized": float(filing.wage_annualized),
                            "pw_annualized": float(filing.pw_annualized),
                        },
                        filing.id,
                    )
                )
                break

    # -- RESIDENTIAL_ADDRESS -------------------------------------------------
    if employer.address_type == "RESIDENTIAL":
        outputs.append(
            (
                ANOMALY_FLAGS["RESIDENTIAL_ADDRESS"],
                {"address_type": employer.address_type, "address": employer.address_line1},
                None,
            )
        )

    # -- SHARED_ADDRESS_CLUSTER ---------------------------------------------
    addr_key = f"{employer.address_line1}|{employer.city}|{employer.state}|{employer.zip}"
    if addr_key in address_clusters:
        outputs.append(
            (
                ANOMALY_FLAGS["SHARED_ADDRESS_CLUSTER"],
                {"address_key": addr_key},
                None,
            )
        )

    # -- VIRTUAL_OFFICE ------------------------------------------------------
    if employer.address_type == "VIRTUAL":
        outputs.append(
            (
                ANOMALY_FLAGS["VIRTUAL_OFFICE"],
                {"address": employer.address_line1},
                None,
            )
        )

    # -- NEW_ENTITY_IMMEDIATE_FILING ----------------------------------------
    sos_rows = session.execute(
        select(SosEntity).where(SosEntity.employer_id == employer.id)
    ).scalars().all()
    if employer.first_filing_date:
        for sos in sos_rows:
            if not sos.formation_date:
                continue
            gap = employer.first_filing_date - sos.formation_date
            if timedelta(days=0) <= gap <= timedelta(days=90):
                outputs.append(
                    (
                        ANOMALY_FLAGS["NEW_ENTITY_IMMEDIATE_FILING"],
                        {
                            "formation_date": sos.formation_date.isoformat(),
                            "first_filing_date": employer.first_filing_date.isoformat(),
                            "gap_days": gap.days,
                        },
                        None,
                    )
                )
                break

    # -- STAFFING_NO_CLIENT --------------------------------------------------
    if employer.naics_code in STAFFING_NAICS:
        missing = [f for f in filings if not f.secondary_entity]
        if filings and len(missing) / len(filings) > 0.7:
            outputs.append(
                (
                    ANOMALY_FLAGS["STAFFING_NO_CLIENT"],
                    {
                        "naics": employer.naics_code,
                        "missing_secondary_count": len(missing),
                        "total_filings": len(filings),
                    },
                    None,
                )
            )

    # -- HIGH_DENIAL_RATE ----------------------------------------------------
    stats_rows = session.execute(
        select(
            func.sum(UscisEmployerStats.initial_approvals),
            func.sum(UscisEmployerStats.initial_denials),
        ).where(UscisEmployerStats.employer_id == employer.id)
    ).one()
    approvals = int(stats_rows[0] or 0)
    denials = int(stats_rows[1] or 0)
    total = approvals + denials
    if total >= 10:
        emp_rate = denials / total
        primary_soc = None
        if filings:
            primary_soc = Counter(
                f.soc_code for f in filings if f.soc_code
            ).most_common(1)
            primary_soc = primary_soc[0][0] if primary_soc else None
        avg = soc_denial_rates.get(primary_soc) if primary_soc else None
        if avg and emp_rate > 2 * avg:
            outputs.append(
                (
                    ANOMALY_FLAGS["HIGH_DENIAL_RATE"],
                    {
                        "employer_denial_rate": emp_rate,
                        "soc_avg": avg,
                        "soc_code": primary_soc,
                    },
                    None,
                )
            )

    # -- VOLUME_SPIKE --------------------------------------------------------
    by_year: Counter[int] = Counter()
    for f in filings:
        if f.fiscal_year:
            by_year[f.fiscal_year] += 1
    years_sorted = sorted(by_year)
    for prev, curr in zip(years_sorted, years_sorted[1:]):
        if by_year[prev] >= 5 and by_year[curr] > 3 * by_year[prev]:
            outputs.append(
                (
                    ANOMALY_FLAGS["VOLUME_SPIKE"],
                    {
                        "prev_year": prev,
                        "prev_count": by_year[prev],
                        "curr_year": curr,
                        "curr_count": by_year[curr],
                    },
                    None,
                )
            )
            break

    # -- POST_SANCTION_FILING -----------------------------------------------
    violations = session.execute(
        select(Violation).where(Violation.employer_id == employer.id)
    ).scalars().all()
    for v in violations:
        cutoff = v.debarment_start or v.violation_date
        if not cutoff:
            continue
        post = [f for f in filings if f.received_date and f.received_date > cutoff]
        if post:
            outputs.append(
                (
                    ANOMALY_FLAGS["POST_SANCTION_FILING"],
                    {
                        "violation_date": cutoff.isoformat(),
                        "post_sanction_filings": len(post),
                    },
                    None,
                )
            )
            break

    # -- CONNECTED_TO_VIOLATOR ----------------------------------------------
    if violator_ids and employer.id not in violator_ids:
        graph = subgraph_for_employer(employer.id, max_depth=2)
        for node in graph["nodes"]:
            if node["id"] == employer.id:
                continue
            if node["id"] in violator_ids:
                # Find strongest edge type connecting us (best guess)
                edge = next(
                    (e for e in graph["edges"]
                     if (e["source"] == employer.id and e["target"] == node["id"])
                     or (e["target"] == employer.id and e["source"] == node["id"])),
                    None,
                )
                weight = RELATIONSHIP_WEIGHTS.get(edge["type"] if edge else "", 0.5)
                base = ANOMALY_FLAGS["CONNECTED_TO_VIOLATOR"]
                outputs.append(
                    (
                        FlagDefinition(
                            type=base.type,
                            severity=base.severity,
                            score=round(base.score * weight, 2),
                            description=base.description,
                        ),
                        {
                            "violator_employer_id": node["id"],
                            "relationship_type": edge["type"] if edge else None,
                            "weight": weight,
                            "depth": node["depth"],
                        },
                        None,
                    )
                )
                break

    return outputs


def persist_flags(
    session: Session, employer: Employer, outputs: Iterable[FlagOutput]
) -> float:
    """Persist flag rows and return total (capped) employer anomaly score."""
    # Clear previously stored flags so scoring is idempotent.
    session.query(AnomalyFlag).filter(AnomalyFlag.employer_id == employer.id).delete()
    total = 0.0
    for flag, evidence, lca_id in outputs:
        total += float(flag.score)
        session.add(
            AnomalyFlag(
                employer_id=employer.id,
                lca_filing_id=lca_id,
                flag_type=flag.type,
                flag_severity=flag.severity,
                flag_score=flag.score,
                description=flag.description,
                evidence=evidence,
            )
        )
    total = min(total, 100.0)
    employer.anomaly_score = total
    return total
