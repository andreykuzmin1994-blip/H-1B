"""Normalization helpers for cross-source matching."""
from __future__ import annotations

import re

# Order matters: longer / more specific suffixes first so we strip " LLC" before " L".
_SUFFIXES = [
    " INCORPORATED",
    " CORPORATION",
    " TECHNOLOGIES",
    " TECHNOLOGY",
    " CONSULTANTS",
    " CONSULTING",
    " SOLUTIONS",
    " SERVICES",
    " HOLDINGS",
    " COMPANY",
    " SYSTEMS",
    " GROUP",
    " L.L.C",
    " L L C",
    " PLC",
    " LLP",
    " LLC",
    " LTD",
    " INC",
    " CORP",
    " LP",
    " PC",
    " PA",
    " CO",
]

_PUNCT_CHARS = [",", ".", '"', "'", "(", ")", "&", "*", "/", "\\"]
_WHITESPACE = re.compile(r"\s+")


def normalize_employer_name(name: str | None) -> str:
    """Normalize employer name for cross-source matching.

    Mirrors the spec:
        - uppercase
        - strip common legal-entity suffixes
        - strip punctuation
        - collapse whitespace
    """
    if not name:
        return ""
    out = name.upper().strip()
    # Strip suffixes repeatedly (handles "FOO INC CORP")
    changed = True
    while changed:
        changed = False
        for suffix in _SUFFIXES:
            if suffix in out:
                out = out.replace(suffix, "")
                changed = True
    for ch in _PUNCT_CHARS:
        out = out.replace(ch, "")
    out = _WHITESPACE.sub(" ", out).strip()
    return out


def normalize_address(
    line1: str | None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
) -> str:
    """Normalize an address into a single comparable string."""
    parts = []
    for part in (line1, city, state, zip_code):
        if part:
            cleaned = part.upper()
            for ch in _PUNCT_CHARS:
                cleaned = cleaned.replace(ch, " ")
            cleaned = _WHITESPACE.sub(" ", cleaned).strip()
            if cleaned:
                parts.append(cleaned)
    return " | ".join(parts)
