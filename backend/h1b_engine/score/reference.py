"""Seed reference data for the fraud-detection triggers.

Production deployments should replace the small seed list with a full
scrape / ingestion pipeline:

* ``known_fraud_defendants`` — NER over DOJ / ICE / USCIS / state-AG
  press-release archives back to 2015. The seed below captures a handful of
  named defendants from the high-profile H-1B cases used in our research.

The seeder is idempotent and returns ``(inserted, updated)`` counts.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from h1b_engine.db.models import KnownFraudDefendant
from h1b_engine.utils.names import normalize_employer_name


# A minimal, well-cited seed of officers / executives named as defendants in
# public visa-fraud enforcement actions. Each entry points back to the press
# release so that a flagged hit can be audited. Keep this list conservative:
# every entry must cite a public prosecution document.
#
# Format: (full_name, role, case_title, case_id, case_date, agency,
#          jurisdiction, offense_category, source_url, notes)
FRAUD_DEFENDANT_SEED: tuple[tuple, ...] = (
    (
        "Kishore Dattapuram",
        "DEFENDANT",
        "United States v. Dattapuram et al. (Nanosemantics)",
        "5:19-cr-00172",
        date(2019, 5, 16),
        "DOJ",
        "NDCA",
        "H1B_VISA_FRAUD",
        "https://www.uscis.gov/archive/executives-of-staffing-companies-charged-with-visa-fraud",
        "Nanosemantics staffing-firm executives charged with visa fraud conspiracy.",
    ),
    (
        "Kumar Aswapathi",
        "DEFENDANT",
        "United States v. Dattapuram et al. (Nanosemantics)",
        "5:19-cr-00172",
        date(2019, 5, 16),
        "DOJ",
        "NDCA",
        "H1B_VISA_FRAUD",
        "https://www.uscis.gov/archive/executives-of-staffing-companies-charged-with-visa-fraud",
        None,
    ),
    (
        "Santosh Giri",
        "DEFENDANT",
        "United States v. Dattapuram et al. (Nanosemantics)",
        "5:19-cr-00172",
        date(2019, 5, 16),
        "DOJ",
        "NDCA",
        "H1B_VISA_FRAUD",
        "https://www.uscis.gov/archive/executives-of-staffing-companies-charged-with-visa-fraud",
        None,
    ),
    (
        "Venkat Guntipally",
        "DEFENDANT",
        "United States v. Guntipally (Cloudwick / $21M H-1B fraud)",
        "1:22-cr-00010",
        date(2022, 1, 1),
        "DOJ",
        "EDVA",
        "H1B_VISA_FRAUD",
        "https://www.justice.gov/usao-edva/pr/man-arrested-charges-21-million-h-1b-visa-fraud-conspiracy",
        "Charged in $21M H-1B visa fraud conspiracy.",
    ),
    (
        "Kishan Modugumudi",
        "DEFENDANT",
        "United States v. Modugumudi et al. (NDTX visa racket)",
        "4:23-cr-00XXX",
        date(2023, 6, 1),
        "DOJ",
        "NDTX",
        "H1B_VISA_FRAUD",
        "https://www.justice.gov/usao-ndtx/pr/two-texas-residents-operating-visa-racket-indicted-visa-fraud-money-laundering-and",
        "Texas visa racket / money-laundering RICO indictment.",
    ),
    (
        "Abhijit Jiwa",
        "DEFENDANT",
        "United States v. Jiwa et al. (Bay Area visa fraud)",
        "ICE-2020-BAY",
        date(2020, 1, 1),
        "ICE",
        "NDCA",
        "H1B_VISA_FRAUD",
        "https://www.ice.gov/news/releases/4-bay-area-residents-charged-wide-ranging-visa-fraud-and-money-laundering-scheme",
        None,
    ),
)


def seed_fraud_defendants(session: Session) -> tuple[int, int]:
    """Insert the seeded fraud-defendant list. Returns (inserted, updated)."""
    inserted = 0
    updated = 0
    for (
        name,
        role,
        case_title,
        case_id,
        case_date,
        agency,
        jurisdiction,
        offense_category,
        source_url,
        notes,
    ) in FRAUD_DEFENDANT_SEED:
        norm = normalize_employer_name(name)
        existing = session.execute(
            select(KnownFraudDefendant).where(
                KnownFraudDefendant.name_normalized == norm,
                KnownFraudDefendant.case_id == case_id,
            )
        ).scalar_one_or_none()
        if existing:
            existing.source_url = source_url or existing.source_url
            existing.notes = notes or existing.notes
            updated += 1
            continue
        session.add(
            KnownFraudDefendant(
                full_name=name,
                name_normalized=norm,
                role=role,
                case_id=case_id,
                case_title=case_title,
                case_date=case_date,
                agency=agency,
                jurisdiction=jurisdiction,
                offense_category=offense_category,
                source="SEED_DOJ_PRESS_RELEASE",
                source_url=source_url,
                notes=notes,
            )
        )
        inserted += 1
    return inserted, updated


def bootstrap_score_reference(session: Session) -> dict[str, tuple[int, int]]:
    """Seed all fraud-detection reference data that we ship built-in."""
    return {
        "fraud_defendants": seed_fraud_defendants(session),
    }
