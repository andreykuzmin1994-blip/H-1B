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
