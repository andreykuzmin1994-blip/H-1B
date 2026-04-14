"""Geocoding + address classification.

Uses Nominatim (free) for lat/lng and Smarty for residential vs commercial
classification when credentials are present. Falls back to heuristics and a
known virtual-office provider list when credentials are unavailable so the
pipeline still produces useful address labels in dev.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests
from sqlalchemy import select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer

log = logging.getLogger(__name__)

VIRTUAL_OFFICE_KEYWORDS = (
    "REGUS",
    "WEWORK",
    "WE WORK",
    "SPACES",
    "SERVCORP",
    "DAVINCI",
    "ALLIANCE VIRTUAL",
    "IPOSTAL1",
    "IPOSTAL 1",
    "POSTSCANMAIL",
    "POST SCAN MAIL",
    "THE UPS STORE",
    "UPS STORE",
    "MAIL BOXES ETC",
    "MAILBOX",
    "PMB",
    "PHYSICALADDRESS",
    "OPUS VIRTUAL OFFICES",
    "VIRTUAL OFFICE",
)

RESIDENTIAL_INDICATORS = (" APT ", " APARTMENT ", " UNIT ", "#", " SUITE ", " STE ")


@dataclass
class AddressInfo:
    lat: float | None
    lng: float | None
    address_type: str  # COMMERCIAL|RESIDENTIAL|VIRTUAL|UNKNOWN
    provider: str


def heuristic_classify(address: str | None) -> str:
    if not address:
        return "UNKNOWN"
    upper = f" {address.upper()} "
    for kw in VIRTUAL_OFFICE_KEYWORDS:
        if f" {kw} " in upper or upper.endswith(f" {kw}"):
            return "VIRTUAL"
    for indicator in RESIDENTIAL_INDICATORS:
        if indicator in upper:
            return "RESIDENTIAL"
    return "UNKNOWN"


def nominatim_geocode(address: str) -> tuple[float, float] | None:
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers={"User-Agent": "h1b-transparency/0.1"},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return None
        r = results[0]
        return float(r["lat"]), float(r["lon"])
    except Exception as exc:
        log.warning("Nominatim geocode failed: %s", exc)
        return None


def smarty_classify(street: str, city: str, state: str, zip_: str) -> str | None:
    auth_id = os.environ.get("SMARTY_AUTH_ID")
    auth_token = os.environ.get("SMARTY_AUTH_TOKEN")
    if not auth_id or not auth_token:
        return None
    try:
        resp = requests.get(
            "https://us-street.api.smarty.com/street-address",
            params={
                "auth-id": auth_id,
                "auth-token": auth_token,
                "street": street,
                "city": city,
                "state": state,
                "zipcode": zip_,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        first = data[0]
        metadata = first.get("metadata", {})
        if metadata.get("rdi") == "Residential":
            return "RESIDENTIAL"
        if metadata.get("rdi") == "Commercial":
            return "COMMERCIAL"
    except Exception as exc:
        log.warning("Smarty classify failed: %s", exc)
    return None


def classify_employer(employer: Employer) -> AddressInfo:
    provider = "heuristic"
    address_line = " ".join(
        [p for p in (employer.address_line1, employer.city, employer.state, employer.zip) if p]
    )

    # 1. Try Smarty for classification
    cls = None
    if employer.address_line1 and employer.city and employer.state and employer.zip:
        cls = smarty_classify(
            employer.address_line1, employer.city, employer.state, employer.zip
        )
        if cls:
            provider = "smarty"

    # 2. Fall back to heuristics
    if cls is None:
        cls = heuristic_classify(address_line)

    # 3. Geocode via Nominatim if we don't already have lat/lng
    lat = float(employer.address_geocoded_lat) if employer.address_geocoded_lat else None
    lng = float(employer.address_geocoded_lng) if employer.address_geocoded_lng else None
    if lat is None and address_line:
        coords = nominatim_geocode(address_line)
        if coords:
            lat, lng = coords
            time.sleep(1)  # Nominatim rate limit

    return AddressInfo(lat=lat, lng=lng, address_type=cls, provider=provider)


def run_batch(limit: int | None = None, only_missing: bool = True) -> int:
    """Geocode and classify employer addresses."""
    updated = 0
    with get_session() as session:
        stmt = select(Employer)
        if only_missing:
            stmt = stmt.where(Employer.address_type.is_(None))
        if limit:
            stmt = stmt.limit(limit)
        for employer in session.scalars(stmt):
            info = classify_employer(employer)
            employer.address_type = info.address_type
            if info.lat is not None:
                employer.address_geocoded_lat = info.lat
            if info.lng is not None:
                employer.address_geocoded_lng = info.lng
            updated += 1
    log.info("Address classification complete: %d employers updated", updated)
    return updated
