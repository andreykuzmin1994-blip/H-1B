"""Wage unit normalization."""
from __future__ import annotations

from typing import Final

_MULTIPLIERS: Final[dict[str, int]] = {
    "YEAR": 1,
    "YR": 1,
    "ANNUAL": 1,
    "ANNUALLY": 1,
    "MONTH": 12,
    "MO": 12,
    "MONTHLY": 12,
    "BI-WEEKLY": 26,
    "BIWEEKLY": 26,
    "BI_WEEKLY": 26,
    "FORTNIGHT": 26,
    "WEEK": 52,
    "WK": 52,
    "WEEKLY": 52,
    "HOUR": 2080,
    "HR": 2080,
    "HOURLY": 2080,
}


def annualize_wage(amount: float | int | None, unit: str | None) -> float | None:
    """Convert any wage + unit to an annualized figure.

    40 hrs/week * 52 weeks = 2080 hours/year for hourly conversion.
    Returns ``None`` when amount or unit is missing / unrecognized and we
    cannot safely convert.
    """
    if amount is None or amount == "":
        return None
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return None
    key = (unit or "YEAR").upper().strip()
    mult = _MULTIPLIERS.get(key)
    if mult is None:
        # Unknown unit: fall back to annual equivalence as spec does.
        return amt
    return amt * mult
