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
    parts.append("=== USCIS TIP TEXT ===")
    parts.append(
        "I am submitting this tip based on publicly available DOL / USCIS / BLS "
        "data indicating the following anomalies for the employer identified above:"
    )
    for f in data.get("anomaly_flags", {}).get("flags", []):
        parts.append(f"  - [{f['severity']}] {f['description']}")
    return "\n".join(parts)
