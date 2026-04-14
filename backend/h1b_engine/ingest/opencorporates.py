"""OpenCorporates entity enrichment.

Source: https://api.opencorporates.com/

Free for open-data / public-benefit projects with an API key. We respect rate
limits and cache every successful match into the ``sos_entities`` table.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

import requests
from sqlalchemy import select

from h1b_engine.db.base import get_session
from h1b_engine.db.models import Employer, SosEntity

log = logging.getLogger(__name__)

API_BASE = "https://api.opencorporates.com/v0.4"


def _coerce_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def search_company(name: str, state: str | None = None, api_key: str | None = None) -> list[dict]:
    api_key = api_key or os.environ.get("OPENCORPORATES_API_KEY")
    params: dict[str, Any] = {"q": name}
    if state:
        params["jurisdiction_code"] = f"us_{state.lower()}"
    if api_key:
        params["api_token"] = api_key
    try:
        resp = requests.get(f"{API_BASE}/companies/search", params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", {}).get("companies", [])
    except Exception as exc:
        log.warning("OpenCorporates search failed for %s: %s", name, exc)
        return []


def fetch_company_detail(
    jurisdiction: str, company_number: str, api_key: str | None = None
) -> dict | None:
    api_key = api_key or os.environ.get("OPENCORPORATES_API_KEY")
    params: dict[str, Any] = {}
    if api_key:
        params["api_token"] = api_key
    try:
        resp = requests.get(
            f"{API_BASE}/companies/{jurisdiction}/{company_number}",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("results", {}).get("company")
    except Exception as exc:
        log.warning("OpenCorporates detail fetch failed: %s", exc)
        return None


def fetch_officers(
    jurisdiction: str, company_number: str, api_key: str | None = None
) -> list[dict]:
    api_key = api_key or os.environ.get("OPENCORPORATES_API_KEY")
    params: dict[str, Any] = {}
    if api_key:
        params["api_token"] = api_key
    try:
        resp = requests.get(
            f"{API_BASE}/companies/{jurisdiction}/{company_number}/officers",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return (
            resp.json()
            .get("results", {})
            .get("officers", [])
        )
    except Exception as exc:
        log.warning("OpenCorporates officers fetch failed: %s", exc)
        return []


def enrich_employer(session, employer: Employer, api_key: str | None = None) -> SosEntity | None:
    results = search_company(employer.name, state=employer.state, api_key=api_key)
    if not results:
        return None
    top = results[0].get("company") if "company" in results[0] else results[0]
    jurisdiction = top.get("jurisdiction_code")
    number = top.get("company_number")
    if not jurisdiction or not number:
        return None
    detail = fetch_company_detail(jurisdiction, number, api_key=api_key) or {}
    officers = fetch_officers(jurisdiction, number, api_key=api_key)

    state = jurisdiction.split("_")[-1].upper() if "_" in jurisdiction else None
    entity = SosEntity(
        employer_id=employer.id,
        state=state,
        entity_name=detail.get("name") or top.get("name"),
        entity_type=detail.get("company_type") or top.get("company_type"),
        formation_date=_coerce_date(detail.get("incorporation_date")),
        status=detail.get("current_status") or detail.get("inactive") and "INACTIVE" or "ACTIVE",
        registered_agent=(detail.get("registered_agent_address") or {}).get("street_address"),
        principal_address=(detail.get("registered_address") or {}).get("street_address"),
        officers=[{"name": o.get("name"), "title": o.get("position")} for o in officers],
        source_url=detail.get("opencorporates_url") or top.get("opencorporates_url"),
    )
    session.add(entity)
    return entity


def run_batch(limit: int | None = None, only_missing: bool = True) -> int:
    count = 0
    with get_session() as session:
        stmt = select(Employer)
        if only_missing:
            # Only fetch employers without any SosEntity row yet
            stmt = stmt.where(
                ~Employer.id.in_(select(SosEntity.employer_id).where(SosEntity.employer_id.is_not(None)))
            )
        if limit:
            stmt = stmt.limit(limit)
        for employer in session.scalars(stmt):
            if enrich_employer(session, employer):
                count += 1
    log.info("OpenCorporates enrichment complete: %d employers", count)
    return count
