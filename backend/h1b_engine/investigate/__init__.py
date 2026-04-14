"""AutoResearch investigation framework."""
from h1b_engine.investigate.connectors import (
    AddressVerificationConnector,
    EnforcementConnector,
    EntityGraphConnector,
    InvestigationConnector,
    LCAHistoryConnector,
    OpenCorporatesConnector,
    USCISApprovalConnector,
    WageBenchmarkConnector,
)
from h1b_engine.investigate.report import generate_report, tip_text

__all__ = [
    "AddressVerificationConnector",
    "EnforcementConnector",
    "EntityGraphConnector",
    "InvestigationConnector",
    "LCAHistoryConnector",
    "OpenCorporatesConnector",
    "USCISApprovalConnector",
    "WageBenchmarkConnector",
    "generate_report",
    "tip_text",
]
