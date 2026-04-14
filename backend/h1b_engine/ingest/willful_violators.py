"""DOL Willful Violator list scraper.

Source: https://www.dol.gov/agencies/whd/immigration/h1b/willful-violator-list

Small HTML table of debarred employers. Scrape with BeautifulSoup.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select

from h1b_engine.db.models import Employer, Violation
from h1b_engine.ingest.common import ingestion_run
from h1b_engine.utils import normalize_employer_name

log = logging.getLogger(__name__)

WILLFUL_VIOLATOR_URL = "https://www.dol.gov/agencies/whd/immigration/h1b/willful-violator-list"


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    records: list[dict] = []
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        for row in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            record = dict(zip(headers, cells))
            records.append(record)
    return records


def fetch_html(url: str = WILLFUL_VIOLATOR_URL) -> str:
    resp = requests.get(url, timeout=60, headers={"User-Agent": "h1b-transparency/0.1"})
    resp.raise_for_status()
    return resp.text


def ingest(url: str = WILLFUL_VIOLATOR_URL, html: str | None = None) -> int:
    html = html or fetch_html(url)
    records = parse_html(html)
    rows_out = 0
    with ingestion_run("willful_violators", {"url": url}) as (session, run):
        for rec in records:
            name = rec.get("employer") or rec.get("employer name") or rec.get("name")
            if not name:
                continue
            state = rec.get("state") or rec.get("st")
            start = _parse_date(rec.get("debarment start") or rec.get("violation date"))
            end = _parse_date(rec.get("debarment end") or rec.get("end date"))
            name_norm = normalize_employer_name(name)
            emp = None
            if state:
                emp = session.execute(
                    select(Employer).where(
                        Employer.name_normalized == name_norm,
                        Employer.state == state.strip().upper()[:2],
                    )
                ).scalar_one_or_none()
            violation = Violation(
                employer_id=emp.id if emp else None,
                employer_name_raw=name,
                source="DOL_WILLFUL",
                violation_type="WILLFUL_VIOLATOR",
                violation_date=start,
                debarment_start=start,
                debarment_end=end,
                description=rec.get("violation") or rec.get("description"),
                source_url=url,
            )
            session.add(violation)
            rows_out += 1
        run.rows_in = len(records)
        run.rows_out = rows_out
    log.info("Willful violator ingest complete: %d records", rows_out)
    return rows_out
