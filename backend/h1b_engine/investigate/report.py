"""Assembles connector output into a formatted Investigation Report."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer
from h1b_engine.investigate.connectors import fetch_all


def _rule(title: str) -> str:
    suffix_len = max(1, 63 - len(title) - 4)
    return f"─── {title} {'─' * suffix_len}"


def generate_report(employer_id: int) -> str:
    """Return a human-readable investigation report string."""
    with get_session() as session:
        emp = session.get(Employer, employer_id)
        if not emp:
            return f"Employer {employer_id} not found."
    data = fetch_all(employer_id)
    flags = data["anomaly_flags"]
    lca = data["lca_history"]
    uscis = data["uscis_approvals"]
    wages = data["wage_benchmark"]
    violations = data["enforcement"]
    graph = data["entity_graph"]
    address = data["address_verification"]
    corp = data["opencorporates"]
    layoffs = data.get("layoffs", {"count": 0, "events": [], "concurrent_filings": []})

    lines: list[str] = []
    lines.append("EMPLOYER INVESTIGATION REPORT")
    lines.append("═" * 63)
    lines.append("")
    lines.append(f"Target: {emp.name}")
    if emp.ein:
        lines.append(f"EIN: {emp.ein}")
    if address.get("address"):
        lines.append(f"Address: {address['address']}")
    if emp.naics_code:
        lines.append(f"NAICS: {emp.naics_code} ({emp.industry_description or ''})".rstrip())
    severity = "LOW"
    score = float(emp.anomaly_score or 0)
    if score >= 75:
        severity = "CRITICAL"
    elif score >= 50:
        severity = "HIGH"
    elif score >= 25:
        severity = "MEDIUM"
    lines.append(f"Anomaly Score: {score:.0f} / 100 ({severity})")
    lines.append("")

    # Flags
    lines.append(_rule("ANOMALY FLAGS"))
    lines.append("")
    if flags.get("count", 0) == 0:
        lines.append("No anomaly flags detected.")
    else:
        for f in flags["flags"]:
            lines.append(f"[{f['severity']}] {f['type']} ({f['score']:.0f} pts)")
            lines.append(f"  {f['description']}")
            if f.get("evidence"):
                for k, v in f["evidence"].items():
                    lines.append(f"    - {k}: {v}")
            lines.append("")

    # LCA history
    lines.append(_rule("FILING HISTORY"))
    lines.append("")
    lines.append(f"Total LCAs filed: {lca.get('total', 0)}")
    if lca.get("statuses"):
        status_str = ", ".join(f"{k}: {v}" for k, v in lca["statuses"].items())
        lines.append(f"Case outcomes: {status_str}")
    if lca.get("soc_codes"):
        soc_str = ", ".join(f"{code} ({cnt})" for code, cnt in lca["soc_codes"][:5])
        lines.append(f"Top SOC codes: {soc_str}")
    if lca.get("wage_min") is not None:
        lines.append(
            f"Wage range: ${lca['wage_min']:,.0f} - ${lca['wage_max']:,.0f}"
        )
    if lca.get("top_worksites"):
        lines.append("Top worksites:")
        for ws, cnt in lca["top_worksites"]:
            lines.append(f"  - {ws} ({cnt})")
    lines.append("")

    # USCIS
    lines.append(_rule("USCIS PETITION OUTCOMES"))
    lines.append("")
    if not uscis.get("available"):
        lines.append("No USCIS data on file for this employer.")
    else:
        lines.append(
            f"Initial approvals: {uscis['initial_approvals']} | "
            f"Initial denials: {uscis['initial_denials']} | "
            f"Denial rate: {uscis['initial_denial_rate']*100:.1f}%"
        )
        lines.append(
            f"Continuing approvals: {uscis['continuing_approvals']} | "
            f"Continuing denials: {uscis['continuing_denials']}"
        )
    lines.append("")

    # Entity relationships
    lines.append(_rule("ENTITY RELATIONSHIPS"))
    lines.append("")
    nbr_count = graph.get("neighbor_count", 0)
    lines.append(f"Connected entities within 2 hops: {nbr_count}")
    if graph.get("connected_violators"):
        lines.append("Known violators in neighborhood:")
        for v in graph["connected_violators"][:5]:
            lines.append(f"  - {v['name']} (score: {v['anomaly_score']:.0f})")
    lines.append("")

    # Wages
    lines.append(_rule("WAGE BENCHMARK ANALYSIS"))
    lines.append("")
    if wages.get("comparisons"):
        lines.append(
            f"{'SOC':<12} {'Title':<32} {'Employer':>11} {'Median':>11} {'%Below':>7}"
        )
        for c in wages["comparisons"]:
            title = (c.get("soc_title") or "")[:30]
            emp_w = f"${c['employer_avg_wage']:,.0f}" if c.get("employer_avg_wage") else "-"
            med_w = f"${c['national_median']:,.0f}" if c.get("national_median") else "-"
            pct = f"{c['pct_below_median']:.1f}" if c.get("pct_below_median") is not None else "-"
            lines.append(
                f"{c['soc_code']:<12} {title:<32} {emp_w:>11} {med_w:>11} {pct:>7}"
            )
    else:
        lines.append("No wage benchmark data available.")
    lines.append("")

    # Violations
    lines.append(_rule("VIOLATION HISTORY"))
    lines.append("")
    if violations.get("count", 0) == 0:
        lines.append("No enforcement actions on record.")
    else:
        for v in violations["violations"]:
            lines.append(f"- [{v['source']}] {v.get('type') or 'Violation'}")
            if v.get("date"):
                lines.append(f"  Date: {v['date']}")
            if v.get("back_wages") is not None:
                lines.append(f"  Back wages: ${v['back_wages']:,.2f}")
            if v.get("penalty") is not None:
                lines.append(f"  Penalty: ${v['penalty']:,.2f}")
            if v.get("description"):
                lines.append(f"  {v['description']}")
    lines.append("")

    # Corporate registration
    lines.append(_rule("CORPORATE REGISTRATION"))
    lines.append("")
    if not corp.get("available"):
        lines.append("No OpenCorporates / SOS entity record on file.")
    else:
        lines.append(f"Entity: {corp.get('entity_name')} ({corp.get('entity_type')})")
        if corp.get("formation_date"):
            lines.append(f"Formation date: {corp['formation_date']}")
        if corp.get("status"):
            lines.append(f"Status: {corp['status']}")
        if corp.get("registered_agent"):
            lines.append(f"Registered agent: {corp['registered_agent']}")
        if corp.get("officers"):
            lines.append(f"Officers: {len(corp['officers'])}")
            for o in corp["officers"][:5]:
                lines.append(f"  - {o.get('name')} ({o.get('title')})")
    lines.append("")

    # Layoffs and concurrent H-1B filings
    lines.append(_rule("LAYOFFS AND CONCURRENT H-1B FILINGS"))
    lines.append("")
    if layoffs.get("count", 0) == 0:
        lines.append("No WARN Act layoff notices on record for this employer.")
    else:
        lines.append(
            f"WARN / layoff notices on file: {layoffs['count']} "
            f"({layoffs.get('total_workers_affected', 0):,} US workers affected)"
        )
        for ev in layoffs["events"][:10]:
            lines.append(
                f"- [{ev['source']}] "
                f"effective {ev['effective_date'] or ev['notice_date'] or '-'} "
                f"| {ev.get('workers_affected') or '-'} workers"
                f" | {ev.get('location') or '-'}"
            )
            if ev.get("reason"):
                lines.append(f"    reason: {ev['reason']}")
        concurrent = layoffs.get("concurrent_filings", [])
        if concurrent:
            lines.append("")
            lines.append(
                f"H-1B LCAs filed within +/-90 days of a layoff: {len(concurrent)}"
            )
            lines.append(
                "  (INA section 212(n)(1)(E) non-displacement window for "
                "H-1B-dependent employers)"
            )
            for c in concurrent[:10]:
                lines.append(
                    f"  - LCA {c['lca_case_number']} filed {c['lca_received_date']} "
                    f"(SOC {c['soc_code'] or '-'}, {c['worksite'] or '-'}) "
                    f"— {c['days_between']} days from layoff"
                )
    lines.append("")

    # Address
    lines.append(_rule("ADDRESS VERIFICATION"))
    lines.append("")
    lines.append(f"Classification: {address.get('address_type', 'UNKNOWN')}")
    if address.get("lat"):
        lines.append(f"Coordinates: {address['lat']}, {address['lng']}")
    lines.append(f"Other entities at address: {address.get('other_entities_at_address', 0)}")
    if address.get("visadata_url"):
        lines.append(f"visadata.org lookup: {address['visadata_url']}")
    lines.append("")

    # Recommendation
    lines.append(_rule("RECOMMENDED ACTION"))
    lines.append("")
    recs = _recommendations(flags, lca, wages, violations)
    if recs:
        lines.append("File LCA complaint with DOL Wage and Hour Division citing:")
        for i, r in enumerate(recs, 1):
            lines.append(f"  {i}. {r}")
    else:
        lines.append("No formal action recommended based on current flags.")
    lines.append("")

    lines.append("═" * 63)
    lines.append("Copy-paste text for DOL complaint form and USCIS tip form below.")
    lines.append("═" * 63)
    lines.append("")
    lines.append(tip_text(employer_id, data=data))
    return "\n".join(lines)


def _recommendations(flags, lca, wages, violations) -> list[str]:
    recs: list[str] = []
    flag_types = {f["type"] for f in flags.get("flags", [])}
    if "NAICS_SOC_MISMATCH" in flag_types or "NON_SPECIALTY_SOC" in flag_types:
        recs.append("Misrepresentation of job duties (NAICS-SOC mismatch)")
    if "WAGE_FAR_BELOW_SOC_MEDIAN" in flag_types or "WAGE_BELOW_PREVAILING" in flag_types:
        recs.append("Wage below prevailing wage for occupation and area")
    if "RESIDENTIAL_ADDRESS" in flag_types or "VIRTUAL_OFFICE" in flag_types or "SHARED_ADDRESS_CLUSTER" in flag_types:
        recs.append("Questionable business presence at stated address")
    if "POST_SANCTION_FILING" in flag_types:
        recs.append("Continued filing activity after prior enforcement action")
    if "HIGH_DENIAL_RATE" in flag_types:
        recs.append("High USCIS denial rate relative to peer employers in same SOC")
    if "LAYOFF_WITH_CONCURRENT_H1B" in flag_types:
        recs.append(
            "H-1B filing inside INA section 212(n)(1)(E) 90-day "
            "non-displacement window around a WARN Act layoff notice"
        )
    if "LAYOFF_SAME_WORKSITE_H1B" in flag_types:
        recs.append(
            "H-1B worksite matches the geographic location of a concurrent "
            "US-worker layoff"
        )
    if "LAYOFF_SAME_SOC_H1B" in flag_types:
        recs.append(
            "H-1B occupation overlaps the job family affected by the "
            "concurrent layoff"
        )
    if "COMMON_AGENT_CLUSTER" in flag_types:
        recs.append(
            "Petitioner sits inside an industrialized shell-employer "
            "cluster sharing registered agent and business address with "
            "3+ other petitioners"
        )
    if "OFFICER_PRIOR_VISA_INDICTMENT" in flag_types:
        recs.append(
            "Corporate officer previously named in a DOJ/ICE visa-fraud "
            "enforcement action"
        )
    if "DOL_BENCHING_COMPLAINT_HISTORY" in flag_types:
        recs.append(
            "Prior DOL Wage and Hour Division finding of benching / "
            "nonproductive-status wage violation (20 CFR 655.731)"
        )
    return recs


def tip_text(employer_id: int, data: dict[str, Any] | None = None) -> str:
    """Copy-paste-ready text for the DOL complaint form and USCIS tip form."""
    data = data or fetch_all(employer_id)
    with get_session() as session:
        emp = session.get(Employer, employer_id)
        if not emp:
            return ""
    parts: list[str] = []
    parts.append("=== DOL WH-4 COMPLAINT TEXT ===")
    parts.append(f"Employer: {emp.name}")
    addr_info = data.get("address_verification", {})
    if addr_info.get("address"):
        parts.append(f"Address: {addr_info['address']}")
    parts.append("Alleged violations:")
    for r in _recommendations(
        data.get("anomaly_flags", {}),
        data.get("lca_history", {}),
        data.get("wage_benchmark", {}),
        data.get("enforcement", {}),
    ):
        parts.append(f"  - {r}")
    parts.append("Supporting public-data evidence:")
    for f in data.get("anomaly_flags", {}).get("flags", []):
        parts.append(f"  - {f['type']}: {f['description']}")
    parts.append("")

    # Layoff + concurrent H-1B filing evidence package (INA 212(n)(1)(E)).
    layoffs = data.get("layoffs", {})
    concurrent = layoffs.get("concurrent_filings", []) if layoffs else []
    if concurrent:
        parts.append("=== INA 212(n)(1)(E) DISPLACEMENT COMPLAINT ===")
        parts.append(
            "Under 8 U.S.C. section 1182(n)(1)(E), an H-1B-dependent employer "
            "may not displace a US worker employed by the employer within "
            "the period beginning 90 days before and ending 90 days after "
            "the date of filing of any visa petition supported by the "
            "application. The public record below is consistent with a "
            "violation of this non-displacement attestation:"
        )
        parts.append("")
        parts.append(f"Employer: {emp.name}")
        total_workers = layoffs.get("total_workers_affected") or 0
        parts.append(
            f"WARN notices on record: {layoffs.get('count', 0)} "
            f"({total_workers:,} US workers affected)"
        )
        parts.append(
            f"H-1B LCAs filed inside the 90-day window: {len(concurrent)}"
        )
        parts.append("")
        parts.append("Evidence package (public-data citations):")
        for ev in layoffs.get("events", [])[:5]:
            parts.append(
                f"  - {ev['source']}: effective "
                f"{ev['effective_date'] or ev['notice_date']}, "
                f"{ev.get('workers_affected') or '?'} workers, "
                f"{ev.get('location') or '-'}"
            )
            if ev.get("source_url"):
                parts.append(f"      {ev['source_url']}")
        for c in concurrent[:10]:
            parts.append(
                f"  - LCA {c['lca_case_number']} filed {c['lca_received_date']} "
                f"(SOC {c['soc_code'] or '-'}, {c['worksite'] or '-'}); "
                f"{c['days_between']} days from layoff"
            )
        parts.append("")
        parts.append(
            "Requested action: investigate whether the employer is H-1B-"
            "dependent (per 20 CFR 655.736), and, if so, whether the "
            "laid-off US workers held positions that are essentially "
            "equivalent to those of the H-1B workers whose LCAs are listed "
            "above (per 20 CFR 655.738)."
        )
        parts.append("")

    parts.append("=== USCIS TIP TEXT ===")
    parts.append(
        "I am submitting this tip based on publicly available DOL / USCIS / BLS "
        "data indicating the following anomalies for the employer identified above:"
    )
    for f in data.get("anomaly_flags", {}).get("flags", []):
        parts.append(f"  - [{f['severity']}] {f['description']}")
    return "\n".join(parts)
