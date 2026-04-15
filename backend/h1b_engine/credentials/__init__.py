"""Personnel / credential verification subsystem.

Provides the lookup tool used when an employer-level investigation surfaces
suspicious data and a human investigator needs to pressure-test the
beneficiary's claimed credentials (university, degree, signatory, evaluator,
timeline, identity reuse).
"""
from h1b_engine.credentials.flags import CREDENTIAL_FLAGS, CredentialFlagDefinition
from h1b_engine.credentials.lookup import (
    PersonnelReport,
    lookup_by_name,
    lookup_personnel,
    verify_all_for_employer,
    verify_credentials,
)

__all__ = [
    "CREDENTIAL_FLAGS",
    "CredentialFlagDefinition",
    "PersonnelReport",
    "lookup_by_name",
    "lookup_personnel",
    "verify_all_for_employer",
    "verify_credentials",
]
