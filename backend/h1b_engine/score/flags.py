"""Flag definitions and thresholds for the scoring engine."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FlagDefinition:
    type: str
    severity: str  # CRITICAL|HIGH|MEDIUM|LOW
    score: float
    description: str


ANOMALY_FLAGS: dict[str, FlagDefinition] = {
    "NAICS_SOC_MISMATCH": FlagDefinition(
        type="NAICS_SOC_MISMATCH",
        severity="CRITICAL",
        score=40,
        description="Employer NAICS industry has no plausible connection to filed SOC occupation",
    ),
    "NON_SPECIALTY_SOC": FlagDefinition(
        type="NON_SPECIALTY_SOC",
        severity="HIGH",
        score=25,
        description="Filed SOC code is not classified as requiring a bachelor's degree",
    ),
    "WAGE_FAR_BELOW_SOC_MEDIAN": FlagDefinition(
        type="WAGE_FAR_BELOW_SOC_MEDIAN",
        severity="HIGH",
        score=25,
        description="Offered wage is less than 50% of SOC national median",
    ),
    "WAGE_BELOW_PREVAILING": FlagDefinition(
        type="WAGE_BELOW_PREVAILING",
        severity="MEDIUM",
        score=15,
        description="Offered wage is below DOL prevailing wage for the filing",
    ),
    "RESIDENTIAL_ADDRESS": FlagDefinition(
        type="RESIDENTIAL_ADDRESS",
        severity="HIGH",
        score=20,
        description="Employer address classified as residential property",
    ),
    "SHARED_ADDRESS_CLUSTER": FlagDefinition(
        type="SHARED_ADDRESS_CLUSTER",
        severity="HIGH",
        score=20,
        description="5+ distinct employer names filing from the same address",
    ),
    "VIRTUAL_OFFICE": FlagDefinition(
        type="VIRTUAL_OFFICE",
        severity="MEDIUM",
        score=15,
        description="Address matches known virtual office / mail forwarding provider",
    ),
    "NEW_ENTITY_IMMEDIATE_FILING": FlagDefinition(
        type="NEW_ENTITY_IMMEDIATE_FILING",
        severity="MEDIUM",
        score=15,
        description="Entity formed within 90 days of first LCA filing",
    ),
    "STAFFING_NO_CLIENT": FlagDefinition(
        type="STAFFING_NO_CLIENT",
        severity="MEDIUM",
        score=12,
        description="Staffing/consulting company with no secondary entity listed",
    ),
    "HIGH_DENIAL_RATE": FlagDefinition(
        type="HIGH_DENIAL_RATE",
        severity="MEDIUM",
        score=12,
        description="Denial rate >2x the average for the same SOC code",
    ),
    "VOLUME_SPIKE": FlagDefinition(
        type="VOLUME_SPIKE",
        severity="LOW",
        score=8,
        description="Filing volume increased >300% year-over-year",
    ),
    "POST_SANCTION_FILING": FlagDefinition(
        type="POST_SANCTION_FILING",
        severity="CRITICAL",
        score=35,
        description="Employer or related entity filed LCAs after being sanctioned",
    ),
    "CONNECTED_TO_VIOLATOR": FlagDefinition(
        type="CONNECTED_TO_VIOLATOR",
        severity="HIGH",
        score=18,
        description="Entity shares address/agent/officer with a known violator",
    ),
    "LAYOFF_WITH_CONCURRENT_H1B": FlagDefinition(
        type="LAYOFF_WITH_CONCURRENT_H1B",
        severity="CRITICAL",
        score=40,
        description=(
            "Employer filed an H-1B LCA within the INA 212(n)(1)(E) 90-day "
            "non-displacement window around a WARN Act mass-layoff notice"
        ),
    ),
    "LAYOFF_SAME_WORKSITE_H1B": FlagDefinition(
        type="LAYOFF_SAME_WORKSITE_H1B",
        severity="CRITICAL",
        score=35,
        description=(
            "Concurrent H-1B filing lists the same worksite city/state as the "
            "layoff notice"
        ),
    ),
    "LAYOFF_SAME_SOC_H1B": FlagDefinition(
        type="LAYOFF_SAME_SOC_H1B",
        severity="HIGH",
        score=25,
        description=(
            "Concurrent H-1B filing's SOC major group matches the layoff's "
            "industry/reason signal"
        ),
    ),
    "COMMON_AGENT_CLUSTER": FlagDefinition(
        type="COMMON_AGENT_CLUSTER",
        severity="CRITICAL",
        score=35,
        description=(
            "3+ petitioners share the same registered agent and business "
            "address (industrialized shell-employer cluster pattern)"
        ),
    ),
    "OFFICER_PRIOR_VISA_INDICTMENT": FlagDefinition(
        type="OFFICER_PRIOR_VISA_INDICTMENT",
        severity="CRITICAL",
        score=40,
        description=(
            "Corporate officer named in a prior DOJ/ICE/USCIS visa-fraud "
            "indictment or settlement"
        ),
    ),
    "DOL_BENCHING_COMPLAINT_HISTORY": FlagDefinition(
        type="DOL_BENCHING_COMPLAINT_HISTORY",
        severity="HIGH",
        score=30,
        description=(
            "Prior DOL Wage and Hour Division finding of benching / "
            "nonproductive-status wage violation under 20 CFR 655.731"
        ),
    ),
}

# 90-day non-displacement window from INA section 212(n)(1)(E).
LAYOFF_WINDOW_DAYS: int = 90

# Rough industry/reason-token to SOC major-group map used to detect
# "laid off engineers while filing engineer H-1Bs" patterns. Kept intentionally
# conservative: we only produce the flag when a reasonably specific signal
# overlaps the concurrent LCA's SOC major group.
LAYOFF_REASON_SOC_HINTS: dict[str, set[str]] = {
    "software": {"15"},
    "engineer": {"15", "17"},
    "engineering": {"15", "17"},
    "developer": {"15"},
    "technology": {"15"},
    "tech": {"15"},
    "it": {"15"},
    "data": {"15"},
    "cloud": {"15"},
    "computer": {"15"},
    "information": {"15"},
    "finance": {"13"},
    "financial": {"13"},
    "accounting": {"13"},
    "marketing": {"11", "13"},
    "sales": {"41"},
    "operations": {"11", "43"},
    "manufacturing": {"51"},
    "production": {"51"},
    "warehouse": {"53"},
    "logistics": {"53"},
    "research": {"19"},
}

# Hard-flag NAICS prefix + SOC major-group combinations
NAICS_SOC_HARD_RULES: list[tuple[str, str]] = [
    ("447", "15"),  # gas stations + computer occupations
    ("445", "15"),  # food/beverage retail + computer
    ("811", "15"),  # repair/maintenance + computer
    ("453", "15"),  # misc retail + computer
    ("722", "15"),  # food services + computer
    ("812", "15"),  # personal services + computer
    ("441", "15"),  # motor vehicle dealers + computer
]

# SOC codes for occupations that don't typically require a bachelor's degree.
NON_SPECIALTY_SOCS: set[str] = {
    "41-2011",
    "41-2031",
    "35-1012",
    "35-2014",
    "53-7065",
    "43-4051",
    "43-5081",
    "37-2011",
    "39-9011",
}

# Known staffing / consulting NAICS codes used by the STAFFING_NO_CLIENT rule.
STAFFING_NAICS: set[str] = {"541512", "561320"}

# Default violator-graph relationship weights.
RELATIONSHIP_WEIGHTS: dict[str, float] = {
    "SHARED_OFFICER": 1.0,
    "NAME_VARIANT": 0.9,
    "SHARED_AGENT": 0.8,
    "SHARED_ADDRESS": 0.6,
}

BUSINESS_PARK_KEYWORDS: tuple[str, ...] = (
    "BUSINESS PARK", "INDUSTRIAL PARK", "CORPORATE CENTER",
    "OFFICE PARK", "TECHNOLOGY PARK",
)

# Minimum cluster size for the COMMON_AGENT_CLUSTER detector.
COMMON_AGENT_CLUSTER_THRESHOLD: int = 3

# Substring tokens used to match DOL WHD violation rows for the benching /
# nonproductive-status pattern. Matched case-insensitively against the
# ``violation_type`` and ``description`` fields.
BENCHING_VIOLATION_TOKENS: tuple[str, ...] = (
    "BENCH",
    "NONPRODUCTIVE",
    "NON-PRODUCTIVE",
    "UNPAID WAGES",
    "REQUIRED WAGE",
    "WH-4",
    "WH4",
    "FAILURE TO PAY",
)
