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
    DisciplinedPractitioner,
    Employer,
    EmployerPayrollRecord,
    EntityRelationship,
    H1BRegistration,
    KnownFraudDefendant,
    LayoffEvent,
    LcaFiling,
    SocWageBenchmark,
    SosEntity,
    UscisEmployerStats,
    Violation,
)
from h1b_engine.graph.builder import subgraph_for_employer
from h1b_engine.score.flags import (
    ANOMALY_FLAGS,
    BENCHING_VIOLATION_TOKENS,
    BUSINESS_PARK_KEYWORDS,
    COMMON_AGENT_CLUSTER_THRESHOLD,
    LAYOFF_REASON_SOC_HINTS,
    LAYOFF_WINDOW_DAYS,
    NAICS_SOC_HARD_RULES,
    NON_SPECIALTY_SOCS,
    PAYROLL_GAP_MIN_APPROVALS,
    PAYROLL_GAP_RATIO,
    RELATIONSHIP_WEIGHTS,
    STAFFING_NAICS,
    FlagDefinition,
)
from h1b_engine.utils.names import normalize_employer_name

log = logging.getLogger(__name__)

FlagOutput = tuple[FlagDefinition, dict[str, Any], int | None]  # (flag, evidence, lca_filing_id)


def _related_employer_ids(session: Session, employer_id: int) -> set[int]:
    """Return employer_ids known to be related to ``employer_id`` via the graph.

    Used by the MULTI_REGISTRATION_SAME_BENEFICIARY detector to avoid firing
    when the "other" petitioner is actually a corporate affiliate.
    """
    rows = session.execute(
        select(
            EntityRelationship.employer_id_a, EntityRelationship.employer_id_b
        ).where(
            (EntityRelationship.employer_id_a == employer_id)
            | (EntityRelationship.employer_id_b == employer_id)
        )
    ).all()
    related: set[int] = set()
    for a, b in rows:
        related.add(a)
        related.add(b)
    related.discard(employer_id)
    return related


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
# Multi-registration / agent-cluster / ghost-employer aggregations
# --------------------------------------------------------------------------- #


def compute_multi_registered_beneficiaries(
    session: Session,
) -> dict[int, list[dict[str, Any]]]:
    """Map employer_id -> list of multi-registered beneficiary evidence dicts.

    A beneficiary is "multi-registered" when the same
    ``(normalized_name, dob, cap_year)`` or
    ``(passport_country, passport_last4, cap_year)`` appears on registrations
    from 2+ employer_ids.
    """
    rows = session.execute(select(H1BRegistration)).scalars().all()
    if not rows:
        return {}

    # Group by stable identity key(s).
    name_groups: dict[tuple, list[H1BRegistration]] = defaultdict(list)
    passport_groups: dict[tuple, list[H1BRegistration]] = defaultdict(list)
    for r in rows:
        if r.beneficiary_name_normalized:
            name_groups[
                (
                    r.beneficiary_name_normalized,
                    r.beneficiary_date_of_birth,
                    r.cap_fiscal_year,
                )
            ].append(r)
        if r.passport_country and r.passport_last4:
            passport_groups[
                (r.passport_country, r.passport_last4, r.cap_fiscal_year)
            ].append(r)

    result: dict[int, list[dict[str, Any]]] = defaultdict(list)

    def _record(group: list[H1BRegistration], key_kind: str, key_value: tuple) -> None:
        employer_ids = {r.employer_id for r in group if r.employer_id is not None}
        if len(employer_ids) < 2:
            return
        for r in group:
            if r.employer_id is None:
                continue
            other = sorted(employer_ids - {r.employer_id})
            if not other:
                continue
            result[r.employer_id].append(
                {
                    "cap_fiscal_year": r.cap_fiscal_year,
                    "beneficiary_name_normalized": r.beneficiary_name_normalized,
                    "key_kind": key_kind,
                    "other_employer_ids": other,
                    "registration_ids": [g.id for g in group],
                }
            )

    for key, group in name_groups.items():
        _record(group, "name_dob", key)
    for key, group in passport_groups.items():
        _record(group, "passport", key)

    return dict(result)


def compute_agent_clusters(
    session: Session, threshold: int = COMMON_AGENT_CLUSTER_THRESHOLD
) -> dict[int, dict[str, Any]]:
    """Map employer_id -> cluster evidence for the COMMON_AGENT_CLUSTER rule.

    A cluster is a set of ``>= threshold`` distinct employers sharing the
    same ``(registered_agent, principal_address)`` pair per the
    ``sos_entities`` reference data.
    """
    rows = session.execute(
        select(
            SosEntity.registered_agent,
            SosEntity.principal_address,
            SosEntity.employer_id,
        ).where(
            SosEntity.registered_agent.is_not(None),
            SosEntity.employer_id.is_not(None),
        )
    ).all()

    by_key: dict[tuple[str, str], set[int]] = defaultdict(set)
    for agent, addr, emp_id in rows:
        agent_n = normalize_employer_name(agent)
        addr_n = normalize_employer_name(addr or "")
        by_key[(agent_n, addr_n)].add(emp_id)

    result: dict[int, dict[str, Any]] = {}
    for (agent, addr), emp_ids in by_key.items():
        if len(emp_ids) < threshold:
            continue
        for emp_id in emp_ids:
            peers = sorted(emp_ids - {emp_id})
            result[emp_id] = {
                "registered_agent": agent,
                "principal_address": addr or None,
                "cluster_size": len(emp_ids),
                "peer_employer_ids": peers[:10],
            }
    return result


def compute_fraud_defendant_names(session: Session) -> dict[str, list[dict[str, Any]]]:
    """Normalized-name -> list of fraud-defendant case dicts."""
    rows = session.execute(select(KnownFraudDefendant)).scalars().all()
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_name[r.name_normalized].append(
            {
                "case_id": r.case_id,
                "case_title": r.case_title,
                "agency": r.agency,
                "case_date": r.case_date.isoformat() if r.case_date else None,
                "source_url": r.source_url,
                "role": r.role,
            }
        )
    return dict(by_name)


def compute_disciplined_attorneys(
    session: Session,
) -> dict[str, list[dict[str, Any]]]:
    """Normalized-name -> list of discipline entries for attorney matching."""
    rows = session.execute(select(DisciplinedPractitioner)).scalars().all()
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_name[r.name_normalized].append(
            {
                "bar_id": r.bar_id,
                "jurisdiction": r.jurisdiction,
                "discipline_type": r.discipline_type,
                "effective_date": r.effective_date.isoformat()
                if r.effective_date
                else None,
                "reinstatement_date": r.reinstatement_date.isoformat()
                if r.reinstatement_date
                else None,
                "source_url": r.source_url,
            }
        )
    return dict(by_name)


def compute_payroll_by_employer_year(
    session: Session,
) -> dict[int, dict[int, dict[str, Any]]]:
    """employer_id -> fiscal_year -> {worker_count, total_wages, sources}."""
    rows = session.execute(select(EmployerPayrollRecord)).scalars().all()
    result: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for r in rows:
        if r.employer_id is None:
            continue
        existing = result[r.employer_id].get(r.fiscal_year)
        new_count = int(r.worker_count) if r.worker_count is not None else 0
        new_wages = float(r.total_wages) if r.total_wages is not None else 0.0
        if existing:
            existing["worker_count"] = max(existing["worker_count"], new_count)
            existing["total_wages"] = max(existing["total_wages"], new_wages)
            existing["sources"].add(r.source)
        else:
            result[r.employer_id][r.fiscal_year] = {
                "worker_count": new_count,
                "total_wages": new_wages,
                "sources": {r.source},
            }
    return result


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
    multi_registrations: dict[int, list[dict[str, Any]]] | None = None,
    agent_clusters: dict[int, dict[str, Any]] | None = None,
    fraud_defendants: dict[str, list[dict[str, Any]]] | None = None,
    disciplined_attorneys: dict[str, list[dict[str, Any]]] | None = None,
    payroll_by_year: dict[int, dict[int, dict[str, Any]]] | None = None,
) -> list[FlagOutput]:
    multi_registrations = multi_registrations or {}
    agent_clusters = agent_clusters or {}
    fraud_defendants = fraud_defendants or {}
    disciplined_attorneys = disciplined_attorneys or {}
    payroll_by_year = payroll_by_year or {}
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

    # -- LAYOFF_WITH_CONCURRENT_H1B -----------------------------------------
    # INA section 212(n)(1)(E) prohibits H-1B-dependent employers from
    # displacing US workers within 90 days before or after filing. We flag any
    # LCA filed inside that window around a WARN notice for the same employer,
    # and escalate when the worksite or SOC family overlap.
    layoff_outputs = detect_layoffs_with_concurrent_h1b(session, employer, filings)
    outputs.extend(layoff_outputs)

    # -- MULTI_REGISTRATION_SAME_BENEFICIARY --------------------------------
    multi_hits = multi_registrations.get(employer.id, [])
    if multi_hits:
        # Only surface genuinely unrelated-petitioner collisions: filter out
        # cases where every other petitioner is inside our own entity-graph
        # neighborhood (same family of employers).
        related_ids = _related_employer_ids(session, employer.id)
        external_hits = [
            h for h in multi_hits if set(h["other_employer_ids"]) - related_ids
        ]
        if external_hits:
            hit = external_hits[0]
            outputs.append(
                (
                    ANOMALY_FLAGS["MULTI_REGISTRATION_SAME_BENEFICIARY"],
                    {
                        "cap_fiscal_year": hit["cap_fiscal_year"],
                        "key_kind": hit["key_kind"],
                        "colliding_employer_ids": hit["other_employer_ids"],
                        "total_collisions": len(external_hits),
                    },
                    None,
                )
            )

    # -- COMMON_AGENT_CLUSTER -----------------------------------------------
    cluster = agent_clusters.get(employer.id)
    if cluster:
        outputs.append(
            (
                ANOMALY_FLAGS["COMMON_AGENT_CLUSTER"],
                cluster,
                None,
            )
        )

    # -- OFFICER_PRIOR_VISA_INDICTMENT --------------------------------------
    if fraud_defendants:
        sos_rows_for_match = session.execute(
            select(SosEntity).where(SosEntity.employer_id == employer.id)
        ).scalars().all()
        matched_cases: list[dict[str, Any]] = []
        matched_officer: str | None = None
        for sos in sos_rows_for_match:
            officers = sos.officers or []
            for officer in officers:
                if not isinstance(officer, dict):
                    continue
                officer_name = officer.get("name") or officer.get("full_name")
                if not officer_name:
                    continue
                norm = normalize_employer_name(officer_name)
                if norm in fraud_defendants:
                    matched_officer = officer_name
                    matched_cases = fraud_defendants[norm]
                    break
            if matched_cases:
                break
        if matched_cases:
            outputs.append(
                (
                    ANOMALY_FLAGS["OFFICER_PRIOR_VISA_INDICTMENT"],
                    {
                        "matched_officer": matched_officer,
                        "matched_cases": matched_cases[:5],
                    },
                    None,
                )
            )

    # -- NO_PAYROLL_FOR_H1B_VOLUME -----------------------------------------
    payroll_years = payroll_by_year.get(employer.id, {})
    uscis_by_year = session.execute(
        select(
            UscisEmployerStats.fiscal_year,
            func.sum(UscisEmployerStats.initial_approvals),
        )
        .where(UscisEmployerStats.employer_id == employer.id)
        .group_by(UscisEmployerStats.fiscal_year)
    ).all()
    for fy, approvals in uscis_by_year:
        approvals = int(approvals or 0)
        if approvals < PAYROLL_GAP_MIN_APPROVALS:
            continue
        payroll = payroll_years.get(fy)
        worker_count = payroll["worker_count"] if payroll else 0
        if worker_count == 0 or approvals > PAYROLL_GAP_RATIO * worker_count:
            outputs.append(
                (
                    ANOMALY_FLAGS["NO_PAYROLL_FOR_H1B_VOLUME"],
                    {
                        "fiscal_year": fy,
                        "h1b_initial_approvals": approvals,
                        "reported_worker_count": worker_count,
                        "payroll_sources": sorted(payroll["sources"])
                        if payroll
                        else [],
                    },
                    None,
                )
            )
            break

    # -- PREPARER_ON_EOIR_DISCIPLINE_LIST -----------------------------------
    if disciplined_attorneys:
        attorney_hit: tuple[str, dict[str, Any]] | None = None
        for filing in filings:
            norm = filing.attorney_name_normalized
            if not norm:
                continue
            records = disciplined_attorneys.get(norm)
            if records:
                attorney_hit = (filing.attorney_name or norm, records[0])
                break
        if attorney_hit:
            attorney_label, record = attorney_hit
            outputs.append(
                (
                    ANOMALY_FLAGS["PREPARER_ON_EOIR_DISCIPLINE_LIST"],
                    {
                        "attorney": attorney_label,
                        "discipline_type": record.get("discipline_type"),
                        "jurisdiction": record.get("jurisdiction"),
                        "effective_date": record.get("effective_date"),
                        "source_url": record.get("source_url"),
                    },
                    None,
                )
            )

    # -- DOL_BENCHING_COMPLAINT_HISTORY -------------------------------------
    benching_hits = []
    for v in session.execute(
        select(Violation).where(Violation.employer_id == employer.id)
    ).scalars().all():
        haystack = " ".join(
            filter(None, [v.violation_type or "", v.description or ""])
        ).upper()
        if any(token in haystack for token in BENCHING_VIOLATION_TOKENS):
            benching_hits.append(v)
    if benching_hits:
        v = benching_hits[0]
        outputs.append(
            (
                ANOMALY_FLAGS["DOL_BENCHING_COMPLAINT_HISTORY"],
                {
                    "source": v.source,
                    "violation_type": v.violation_type,
                    "violation_date": v.violation_date.isoformat()
                    if v.violation_date
                    else None,
                    "back_wages": float(v.back_wages_amount)
                    if v.back_wages_amount
                    else None,
                    "count": len(benching_hits),
                },
                None,
            )
        )

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


def _soc_hints_for_reason(text: str | None) -> set[str]:
    """Return candidate SOC major groups implied by a WARN reason/industry string."""
    if not text:
        return set()
    tokens = text.lower()
    hints: set[str] = set()
    for keyword, major_groups in LAYOFF_REASON_SOC_HINTS.items():
        if keyword in tokens:
            hints.update(major_groups)
    return hints


def detect_layoffs_with_concurrent_h1b(
    session: Session,
    employer: Employer,
    filings: list[LcaFiling],
) -> list[FlagOutput]:
    """Flag employers filing LCAs inside the 90-day non-displacement window.

    Emits up to three stacking flags per employer (most severe first):

    * ``LAYOFF_WITH_CONCURRENT_H1B`` — any LCA within +/- 90 days of the
      layoff's effective date.
    * ``LAYOFF_SAME_WORKSITE_H1B`` — concurrent LCA's worksite matches the
      layoff city+state.
    * ``LAYOFF_SAME_SOC_H1B`` — concurrent LCA's SOC major group matches a
      hint inferred from the layoff's reason/industry text.
    """
    outputs: list[FlagOutput] = []
    if not filings:
        return outputs

    layoffs = session.execute(
        select(LayoffEvent).where(LayoffEvent.employer_id == employer.id)
    ).scalars().all()
    if not layoffs:
        return outputs

    window = timedelta(days=LAYOFF_WINDOW_DAYS)

    concurrent_evidence: dict[str, Any] | None = None
    same_worksite_evidence: dict[str, Any] | None = None
    same_soc_evidence: dict[str, Any] | None = None
    concurrent_lca_id: int | None = None

    for layoff in layoffs:
        pivot = layoff.effective_date or layoff.notice_date
        if not pivot:
            continue
        layoff_city = (layoff.location_city or "").strip().upper()
        layoff_state = (layoff.location_state or "").strip().upper()
        soc_hints = _soc_hints_for_reason(
            " ".join(filter(None, [layoff.reason, layoff.industry]))
        )

        for filing in filings:
            if not filing.received_date:
                continue
            delta = abs((filing.received_date - pivot).days)
            if delta > LAYOFF_WINDOW_DAYS:
                continue

            # Base concurrency evidence — keep the tightest (smallest delta) hit.
            base_payload = {
                "layoff_event_id": layoff.id,
                "layoff_effective_date": pivot.isoformat(),
                "layoff_workers_affected": layoff.workers_affected,
                "layoff_source": layoff.source,
                "lca_case_number": filing.case_number,
                "lca_received_date": filing.received_date.isoformat(),
                "lca_soc_code": filing.soc_code,
                "days_between": delta,
                "direction": (
                    "before_layoff"
                    if filing.received_date < pivot
                    else "after_layoff"
                    if filing.received_date > pivot
                    else "same_day"
                ),
            }
            if (
                concurrent_evidence is None
                or delta < concurrent_evidence["days_between"]
            ):
                concurrent_evidence = base_payload
                concurrent_lca_id = filing.id

            # Same-worksite escalation.
            filing_city = (filing.worksite_city or "").strip().upper()
            filing_state = (filing.worksite_state or "").strip().upper()
            if (
                layoff_city
                and layoff_state
                and filing_city == layoff_city
                and filing_state == layoff_state
            ):
                payload = {
                    **base_payload,
                    "worksite_city": filing.worksite_city,
                    "worksite_state": filing.worksite_state,
                }
                if (
                    same_worksite_evidence is None
                    or delta < same_worksite_evidence["days_between"]
                ):
                    same_worksite_evidence = payload

            # Same-SOC-family escalation.
            if soc_hints and filing.soc_code:
                soc_major = (
                    filing.soc_code.split("-")[0]
                    if "-" in filing.soc_code
                    else filing.soc_code[:2]
                )
                if soc_major in soc_hints:
                    payload = {
                        **base_payload,
                        "soc_major": soc_major,
                        "layoff_reason": layoff.reason,
                        "layoff_industry": layoff.industry,
                    }
                    if (
                        same_soc_evidence is None
                        or delta < same_soc_evidence["days_between"]
                    ):
                        same_soc_evidence = payload

    if concurrent_evidence is not None:
        outputs.append(
            (
                ANOMALY_FLAGS["LAYOFF_WITH_CONCURRENT_H1B"],
                concurrent_evidence,
                concurrent_lca_id,
            )
        )
    if same_worksite_evidence is not None:
        outputs.append(
            (
                ANOMALY_FLAGS["LAYOFF_SAME_WORKSITE_H1B"],
                same_worksite_evidence,
                None,
            )
        )
    if same_soc_evidence is not None:
        outputs.append(
            (ANOMALY_FLAGS["LAYOFF_SAME_SOC_H1B"], same_soc_evidence, None)
        )
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
