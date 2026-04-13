# H-1B Transparency & Accountability Engine

## Project spec for Claude Code implementation

---

## What this is

A public-interest tool that connects three layers of H-1B program data into a single system that surfaces anomalies, maps entity relationships, and generates formatted enforcement tips. Not a fraud detector competing with Project Firewall — a transparency layer that feeds the existing enforcement pipeline.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                          │
│                                                                 │
│  ┌── TIER 1: Bulk Downloads (free, no auth) ──────────────────┐ │
│  │  DOL OFLC LCA Disclosure Data (Excel/CSV, ~800K rows/yr)  │ │
│  │  USCIS H-1B Employer Data Hub (CSV, FY2009-FY2026 Q1)     │ │
│  │  DOL WHD Enforcement Data (CSV, FY2005+)                   │ │
│  │  DOL Willful Violator List (HTML scrape)                   │ │
│  │  BLS OEWS Wage Data (Excel, ~830 SOC codes, national+MSA) │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌── TIER 2: APIs (free or low-cost) ─────────────────────────┐ │
│  │  DOL Data Portal API (no key, REST, incremental updates)   │ │
│  │  OpenCorporates API (free for public benefit, key required)│ │
│  │  Geocoding: Smarty / Nominatim / Google Geocoding API      │ │
│  │  USPS Address API (free, address validation)               │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌── TIER 3: Direct State Registries (Phase 2) ──────────────┐ │
│  │  FL Sunbiz, TX Comptroller, WA SOS, IA SOS, CO SOS        │ │
│  │  (officers, registered agents, formation dates)            │ │
│  └────────────────────────────────────────────────────────────┘ │
│  ┌── REFERENCE (not data sources — UX/integration targets) ──┐ │
│  │  visadata.org — crowdsourced address verification          │ │
│  │  h1bdata.info — 4.8M LCA search (UX benchmark)            │ │
│  │  h1bgrader.com — employer grades (competitor analysis)     │ │
│  │  Kaggle H-1B datasets — pre-cleaned for prototyping        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                          │                                      │
│                    Normalize + Enrich                            │
│                          │                                      │
│                     PostgreSQL                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                      ANALYSIS LAYER                             │
│                                                                 │
│  Entity Graph Builder ──▶ Neo4j or PostgreSQL JSONB             │
│    - shared addresses                                           │
│    - shared registered agents                                   │
│    - shared officers/directors                                  │
│    - FEIN pattern clustering                                    │
│                                                                 │
│  Anomaly Scorer ──▶ per-employer risk score                     │
│    - NAICS-SOC mismatch                                         │
│    - wage vs SOC median deviation                               │
│    - filing velocity vs business size                           │
│    - denial rate vs peer group                                  │
│    - address type classification                                │
│    - entity graph connectivity to known violators               │
│                                                                 │
│  Violator Tracker ──▶ sanctions + continued filing detection    │
│    - post-sanction filing activity                              │
│    - entity name variations after enforcement                   │
│    - sibling entity identification                              │
└─────────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────────┐
│                       OUTPUT LAYER                              │
│                                                                 │
│  Web Dashboard (Next.js)                                        │
│    - employer search + profile pages                            │
│    - anomaly heatmap by geography                               │
│    - entity relationship graph visualization                    │
│    - violator timeline tracker                                  │
│                                                                 │
│  Tip Generator                                                  │
│    - formatted DOL Form WH-4 output                             │
│    - USCIS online tip form pre-fill                             │
│    - 20 CFR § 655.805 complaint template                        │
│    - evidence package assembly                                  │
│                                                                 │
│  API (public, rate-limited)                                     │
│    - /employer/{ein} — full profile + risk score                │
│    - /address/{hash} — all entities at address                  │
│    - /graph/{ein} — entity relationship subgraph                │
│    - /anomalies — filtered feed of flagged filings              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Data ingestion pipeline

### 1.1 Data sources — Complete inventory

#### TIER 1: Primary Government Sources (bulk download, free, no auth)

**DOL OFLC LCA Disclosure Data** ⭐ CORE DATASET
- URL: `https://www.dol.gov/agencies/eta/foreign-labor/performance`
- Format: Excel/CSV, quarterly releases, ~800K+ records per fiscal year
- Coverage: FY2008 through FY2025 full year available (FY2026 Q1-Q3 partial)
- Access: Direct download links on the Performance Data page. Expand "Disclosure Data" tab for current year. Scroll to "LCA Programs (H-1B, H-1B1, E-3)" for prior years.
- Download strategy: Get FY2020-FY2025 full year files (6 files, ~4.5M records total). Each file is a single Excel workbook.
- Record layouts: Published alongside each file as separate PDFs describing every column. Column names shift slightly between years — normalize during ingestion.
- Key fields:
  - `CASE_NUMBER` — unique LCA identifier (format: I-XXX-XXXXX-XXXXXX)
  - `CASE_STATUS` — CERTIFIED, DENIED, WITHDRAWN, CERT-WITHDRAWN
  - `EMPLOYER_NAME` — legal business name
  - `EMPLOYER_ADDRESS1`, `EMPLOYER_CITY`, `EMPLOYER_STATE`, `EMPLOYER_POSTAL_CODE`
  - `NAICS_CODE` — employer industry classification
  - `SOC_CODE`, `SOC_TITLE` — Standard Occupational Classification
  - `JOB_TITLE` — free-text job title from employer (often differs from SOC_TITLE)
  - `WAGE_RATE_OF_PAY_FROM` — minimum offered wage
  - `WAGE_UNIT_OF_PAY` — Year, Month, Bi-Weekly, Week, Hour
  - `PREVAILING_WAGE` — DOL prevailing wage for area
  - `PW_UNIT_OF_PAY` — unit for prevailing wage
  - `WORKSITE_CITY`, `WORKSITE_STATE`, `WORKSITE_POSTAL_CODE`
  - `SECONDARY_ENTITY_BUSINESS_NAME` — third-party client (if staffing/consulting placement)
  - `TOTAL_WORKER_POSITIONS` — number of workers covered by this LCA
  - `RECEIVED_DATE`, `DECISION_DATE`
  - `VISA_CLASS` — H-1B, H-1B1, E-3
- Refresh cadence: Quarterly (typically ~2 months after quarter end)
- Notes: This is the same underlying data that h1bdata.info (4.8M records) and h1bgrader.com index. By downloading directly from DOL, you bypass their ToS restrictions and have full bulk access.

**USCIS H-1B Employer Data Hub**
- URL: `https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub`
- Bulk file downloads: `https://www.uscis.gov/archive/h-1b-employer-data-hub-files`
- Format: CSV/Excel, annual files downloadable per fiscal year
- Coverage: FY2009 through FY2026 Q1
- Access: Hub page has a query interface (search by employer, city, state, ZIP, NAICS). Bulk CSV files for each fiscal year available at the archive URL above.
- Key fields: employer name, city, state, ZIP, NAICS, tax ID (last 4 digits), initial approvals, initial denials, continuing approvals, continuing denials, fiscal year
- Why you need it: LCA data shows DOL certification decisions. This shows USCIS petition approval/denial decisions — a different and later stage. An employer can have 100% LCA certification but 80% USCIS denial, which is a major red flag.
- Refresh: Quarterly updates

**DOL WHD Enforcement Data**
- URL: `https://enforcedata.dol.gov/views/data_summary.php`
- Data catalog: `https://enforcedata.dol.gov/views/data_catalogs.php`
- Format: Downloadable CSV
- Coverage: All concluded WHD compliance actions since FY2005
- Access: Download from the data summary page. Also available via the DOL Data Portal API (see Tier 2).
- Key fields: employer name, trade name, city, state, ZIP, NAICS, findings start/end dates, back wages assessed, civil money penalties, number of employees owed back wages, violation types/acts
- Filter: Look for `h1b` or `ina` (Immigration and Nationality Act) in violation type fields to isolate H-1B specific cases
- Notes: This is the real enforcement outcome data — which employers have been investigated and what was found. Cross-reference employer names against your LCA employer table to link violations to filing history.

**DOL Willful Violator List**
- URL: `https://www.dol.gov/agencies/whd/immigration/h1b/willful-violator-list`
- Format: HTML table (scrape with BeautifulSoup)
- Fields: employer name, city, state, violation date, debarment period
- Size: Small dataset (typically <100 entries)
- Refresh: Check monthly
- Notes: These are the worst-case outcomes — employers debarred from the entire H-1B program. Small list but high signal. Critical for the entity graph: check whether debarred employers have sibling entities still filing.

**BLS Occupational Employment and Wage Statistics (OEWS)**
- URL: `https://www.bls.gov/oes/tables.htm`
- Format: Excel files, multiple levels of geographic detail
- Coverage: ~830 occupations, national + state + ~530 MSA level estimates
- Key files to download:
  - `national_M2024_dl.xlsx` — national estimates by SOC code (median, mean, 10th/25th/75th/90th percentiles)
  - `state_M2024_dl.xlsx` — state-level estimates
  - `MSA_M2024_dl.xlsx` — MSA-level estimates (for location-adjusted comparisons)
- Key fields: SOC code, SOC title, employment count, mean annual wage, median annual wage, wage percentiles
- Uses 2018 SOC codes — same classification system as LCA data
- Why you need it: This is your benchmark for "is this wage reasonable for this occupation?" A gas station filing for SOC 15-1252 (Software Developers) at $31K when the national median is $127K is immediately flagged.
- Refresh: Annual (May reference date, published ~March of following year)
- Phase 1: Use national medians. Phase 2: Use MSA-level medians for location-adjusted scoring.

#### TIER 2: APIs (free or low-cost, some require keys)

**DOL Data Portal API**
- Endpoint: `https://apiprod.dol.gov/v4/`
- Documentation: `https://dataportal.dol.gov/pdf/dol-api-user-guide.pdf`
- Dataset catalog: `https://dataportal.dol.gov/datasets`
- Auth: No API key required
- Format: REST API returning JSON
- Contains: 200+ datasets including WHD enforcement data
- Use case: Incremental updates between bulk file downloads. Query for new enforcement actions since your last ingestion rather than re-downloading the entire file.
- Developer resources: `https://usdepartmentoflabor.github.io/DOLAPI/` — SDKs, sample code, documentation

**OpenCorporates API**
- Endpoint: `https://api.opencorporates.com/`
- Documentation: `https://api.opencorporates.com/documentation/API-Reference`
- Auth: API key required. Free for open data / public benefit projects (apply on their site). Paid tiers for commercial use.
- Coverage: 145 jurisdictions including all US states
- Key endpoints:
  - `GET /companies/search?q={name}&jurisdiction_code=us_{state}` — search companies
  - `GET /companies/{jurisdiction}/{company_number}` — company details (formation date, status, registered address, agent)
  - `GET /companies/{jurisdiction}/{company_number}/officers` — officers and directors
  - `GET /companies/{jurisdiction}/{company_number}/filings` — filing history
- Rate limits: Depend on plan tier. Free tier has modest limits.
- Use case: This is the shortcut to entity relationship data. Instead of hitting 50 state SOS registries, query OpenCorporates for every employer in your LCA database, pull officers and registered agents, and build the entity graph. Bellingcat used this for the Panama Papers investigation.
- Open Refine integration: OpenCorporates provides a reconciliation API that lets you batch-match a CSV of employer names to legal entities. Very efficient for the initial entity resolution pass.
- Notes: Data provenance is excellent — every record links back to the original state registry source with retrieval timestamps.

**Geocoding & Address Classification Services**
- Purpose: Classify every employer address as COMMERCIAL, RESIDENTIAL, VIRTUAL, or UNKNOWN. Critical for ghost employer detection.
- Volume estimate: ~30K unique employer addresses across 6 years of LCA data
- Options (in order of recommendation):

  1. **Smarty (formerly SmartyStreets)** — Best for this use case
     - URL: `https://www.smarty.com/`
     - Has `dpv_residential_delivery_indicator` field that directly classifies residential vs commercial
     - 250 free lookups/month, then ~$0.01/lookup
     - Total cost for 30K addresses: ~$300 one-time
     - Also validates whether addresses actually exist (deliverable vs vacant)

  2. **USPS Address API** — Free, limited
     - URL: `https://www.usps.com/business/web-tools-apis/`
     - Free, validates addresses and provides delivery point info
     - Doesn't directly classify residential/commercial as cleanly as Smarty
     - Rate limited

  3. **Nominatim (OpenStreetMap)** — Free, slow
     - URL: `https://nominatim.org/`
     - No API key, no cost
     - Rate limited to 1 request/second (30K addresses = ~8.3 hours)
     - Good for geocoding (lat/lng) but doesn't classify address type
     - Use this for geocoding coordinates, Smarty for classification

  4. **Google Geocoding API** — Expensive overkill
     - $5/1,000 requests = ~$150 for 30K addresses
     - Google Places API `place_details` can distinguish building types but adds another $17/1,000 calls
     - Only use if you need the Google Maps embed on the frontend anyway

  5. **Virtual office provider database** — Manual but valuable
     - Maintain a list of known virtual office / coworking providers: Regus, WeWork, Spaces, Servcorp, Davinci, Alliance Virtual, iPostal1, PostScanMail, The UPS Store
     - Match employer addresses against provider location databases
     - These providers publish their location lists online — scrape once and cache

#### TIER 3: Direct State Registries (Phase 2 — after OpenCorporates gaps identified)

State Secretary of State data varies enormously in accessibility. Use OpenCorporates as the primary aggregation layer, then go direct to these registries only for high-priority states where OpenCorporates data is incomplete or you need deeper filing documents.

**Priority states** (ranked by H-1B filing volume + data accessibility):

| State | Registry | Quality | Bulk Access | Officers | Notes |
|-------|----------|---------|-------------|----------|-------|
| FL | Sunbiz | ★★★★★ | Free search + scanned docs | Yes | Best state registry in the US. Officers, annual reports, all free. |
| TX | Comptroller | ★★★★ | Open data portal bulk download | Yes | Strong. Bulk entity data on Texas open data portal. |
| WA | SOS | ★★★★ | API + bulk | Yes | Scored 80/100 on OpenCorporates openness index. |
| IA | SOS | ★★★★ | Open dataset download | Agent only | Available as open dataset with explicit open license. |
| CO | SOS | ★★★★ | Good online search | Yes | Strong accessibility. |
| CA | SOS | ★★★ | Free PDF docs, limited bulk | Limited | Huge volume but no easy bulk API. 17M+ imaged docs downloadable individually. |
| NJ | SOS | ★★ | Manual search only | Limited | High H-1B volume (Edison, Jersey City body shops) but poor data access. |
| NY | DOS | ★★ | Manual search only | No | Critical market but restricted access. |
| GA | SOS | ★★★ | Decent search | Yes | Relevant for Atlanta-area employers. |
| IL | SOS | ★★★ | Newly opened (2022 law) | Improving | Was worst in nation, now committed to open data. |

**Strategy**: Start with OpenCorporates for all states. Supplement with direct FL Sunbiz and TX Comptroller access (both excellent). Add other direct state integrations only as needed based on gaps in the entity graph.

#### REFERENCE RESOURCES (not data sources — competitive/integration landscape)

**h1bdata.info**
- What it is: Search interface over 4.8M DOL LCA records (Oct 2013 - Sept 2025)
- What it does: Employer name / job title / city search → individual LCA filings with salary, location, status
- What it doesn't do: No anomaly detection, no entity relationships, no NAICS-SOC cross-referencing, no enforcement data, no API, no bulk export
- Data source: Same DOL OFLC disclosure data you'll download directly
- Monetization: Display ads
- Relevance to us: UX benchmark for basic search interface. Shows what a minimal LCA search looks like. Not a data source — pull from DOL directly.

**h1bgrader.com**
- What it is: Employer grading platform for H-1B workers evaluating potential sponsors
- What it does: Combines DOL LCA data + USCIS approval/denial data + prevailing wage data. Assigns letter grades (A-F) to employers based on proprietary scoring algorithm covering approval rates, wage levels, H-1B dependency ratio, willful violator status. Chrome extension overlays H-1B data on LinkedIn and Indeed job listings. LCA case number lookup.
- What it doesn't do: No NAICS-SOC mismatch analysis, no ghost employer detection, no entity relationship mapping, no enforcement tip generation, no address verification
- Data sources: DOL LCA data, USCIS Employer Data Hub, DOL prevailing wage data, DOL willful violator list — all the same sources you'll use
- Monetization: Ads + premium features behind login
- ToS restriction: Explicitly prohibits using their data "in any manner that is a source of or substitute for the Service." Don't scrape them.
- Relevance to us: Competitor analysis for the "employer profile" UX pattern. Their grading methodology is oriented toward job seekers ("is this a good employer to work for?"), not toward fraud detection. Our scoring is fundamentally different — we're looking for anomalies, not quality.

**fraudreporter.visadata.org (H1B Verification System)**
- What it is: Crowdsourced physical verification of H-1B employer addresses
- What it does: Maps LCA employer addresses (2022-2025) with red pins (uninvestigated) and green pins (community-verified). Users physically visit addresses, photograph buildings, upload evidence documenting whether businesses actually exist. Evidence is explicitly shared with DOL and USCIS for formal complaints.
- Companion site: `map.visadata.org` — address map of H-1B LCA employer locations
- What it doesn't do: No data analysis, no entity relationships, no wage scoring, no automated anomaly detection. Purely physical verification.
- Data source: Same DOL LCA address data
- No API: No public API or data export found. Integration would require outreach to their team or building a parallel address verification layer.
- Relevance to us: Most complementary external resource. Our data analysis layer + their physical verification layer = complete picture. Priority integration target. Their verified/unverified address status would add ground-truth to our address classification. Our entity graph context ("14 shell companies at this address, 3 connected to a debarred employer") would make their site visits more targeted.

**Kaggle H-1B Datasets**
- What they are: Pre-cleaned snapshots of DOL LCA data uploaded by researchers
- Notable datasets:
  - `zongaobian/h1b-lca-disclosure-data-2020-2024` — cleaned FY2020-2024
  - `nsharan/h-1b-visa` — petitions 2011-2016
- Useful for: Rapid prototyping. Someone already handled column name normalization across fiscal years and wage unit conversion. Good for building and testing your ingestion pipeline before pointing it at the raw DOL files.
- Limitations: Static snapshots, 1-2 years behind, no enrichment, no enforcement data
- Strategy: Use a Kaggle dataset for Sprint 1 prototyping, then switch to direct DOL downloads for production.

### 1.2 Database schema

```sql
-- Core tables

CREATE TABLE employers (
  id SERIAL PRIMARY KEY,
  ein VARCHAR(20),
  name VARCHAR(500) NOT NULL,
  name_normalized VARCHAR(500) NOT NULL, -- lowercase, stripped punctuation for matching
  address_line1 VARCHAR(500),
  city VARCHAR(200),
  state VARCHAR(2),
  zip VARCHAR(10),
  naics_code VARCHAR(6),
  industry_description VARCHAR(500),
  address_type VARCHAR(20), -- COMMERCIAL, RESIDENTIAL, VIRTUAL, UNKNOWN
  address_geocoded_lat DECIMAL(10,7),
  address_geocoded_lng DECIMAL(10,7),
  first_filing_date DATE,
  last_filing_date DATE,
  total_lca_count INTEGER DEFAULT 0,
  anomaly_score DECIMAL(5,2) DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE lca_filings (
  id SERIAL PRIMARY KEY,
  case_number VARCHAR(50) UNIQUE NOT NULL,
  case_status VARCHAR(20),
  employer_id INTEGER REFERENCES employers(id),
  employer_name_raw VARCHAR(500), -- as filed, before normalization
  naics_code VARCHAR(6),
  soc_code VARCHAR(10),
  soc_title VARCHAR(500),
  job_title VARCHAR(500),
  wage_from DECIMAL(12,2),
  wage_unit VARCHAR(20),
  wage_annualized DECIMAL(12,2), -- normalized to annual
  prevailing_wage DECIMAL(12,2),
  pw_unit VARCHAR(20),
  pw_annualized DECIMAL(12,2), -- normalized to annual
  wage_ratio DECIMAL(5,3), -- wage_annualized / pw_annualized
  worksite_city VARCHAR(200),
  worksite_state VARCHAR(2),
  worksite_zip VARCHAR(10),
  secondary_entity VARCHAR(500),
  total_workers INTEGER,
  visa_class VARCHAR(10),
  received_date DATE,
  decision_date DATE,
  fiscal_year INTEGER,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE violations (
  id SERIAL PRIMARY KEY,
  employer_id INTEGER REFERENCES employers(id),
  source VARCHAR(50), -- DOL_WILLFUL, WHD_ENFORCEMENT, USCIS_DEBARMENT
  violation_type VARCHAR(100),
  violation_date DATE,
  debarment_start DATE,
  debarment_end DATE,
  back_wages_amount DECIMAL(12,2),
  penalty_amount DECIMAL(12,2),
  description TEXT,
  source_url VARCHAR(1000),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE anomaly_flags (
  id SERIAL PRIMARY KEY,
  employer_id INTEGER REFERENCES employers(id),
  lca_filing_id INTEGER REFERENCES lca_filings(id),
  flag_type VARCHAR(50) NOT NULL,
  flag_severity VARCHAR(10), -- CRITICAL, HIGH, MEDIUM, LOW
  flag_score DECIMAL(5,2),
  description TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Entity relationship graph

CREATE TABLE entity_relationships (
  id SERIAL PRIMARY KEY,
  employer_id_a INTEGER REFERENCES employers(id),
  employer_id_b INTEGER REFERENCES employers(id),
  relationship_type VARCHAR(50), -- SHARED_ADDRESS, SHARED_AGENT, SHARED_OFFICER, NAME_VARIANT
  confidence DECIMAL(3,2), -- 0.0 to 1.0
  evidence JSONB, -- { "shared_address": "123 Main St", "agent_name": "John Doe" }
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sos_entities (
  id SERIAL PRIMARY KEY,
  employer_id INTEGER REFERENCES employers(id),
  state VARCHAR(2),
  entity_name VARCHAR(500),
  entity_type VARCHAR(50), -- LLC, CORP, LP
  formation_date DATE,
  status VARCHAR(50), -- ACTIVE, DISSOLVED, REVOKED
  registered_agent VARCHAR(500),
  principal_address VARCHAR(500),
  officers JSONB, -- [{ "name": "...", "title": "..." }]
  source_url VARCHAR(1000),
  fetched_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE soc_wage_benchmarks (
  id SERIAL PRIMARY KEY,
  soc_code VARCHAR(10) NOT NULL,
  soc_title VARCHAR(500),
  oews_year INTEGER NOT NULL, -- e.g. 2024 for May 2024 release
  area_type VARCHAR(20) NOT NULL, -- NATIONAL, STATE, MSA
  area_code VARCHAR(10), -- null for national, state FIPS, or MSA code
  area_name VARCHAR(200),
  employment INTEGER,
  mean_annual_wage DECIMAL(12,2),
  median_annual_wage DECIMAL(12,2),
  pct10_annual_wage DECIMAL(12,2),
  pct25_annual_wage DECIMAL(12,2),
  pct75_annual_wage DECIMAL(12,2),
  pct90_annual_wage DECIMAL(12,2),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(soc_code, oews_year, area_type, area_code)
);

-- Indexes
CREATE INDEX idx_employers_name_norm ON employers(name_normalized);
CREATE INDEX idx_employers_address ON employers(address_line1, city, state);
CREATE INDEX idx_employers_naics ON employers(naics_code);
CREATE INDEX idx_employers_anomaly ON employers(anomaly_score DESC);
CREATE INDEX idx_lca_employer ON lca_filings(employer_id);
CREATE INDEX idx_lca_soc ON lca_filings(soc_code);
CREATE INDEX idx_lca_fiscal_year ON lca_filings(fiscal_year);
CREATE INDEX idx_lca_case_status ON lca_filings(case_status);
CREATE INDEX idx_anomaly_employer ON anomaly_flags(employer_id);
CREATE INDEX idx_anomaly_type ON anomaly_flags(flag_type);
CREATE INDEX idx_entity_rel_a ON entity_relationships(employer_id_a);
CREATE INDEX idx_entity_rel_b ON entity_relationships(employer_id_b);
CREATE INDEX idx_soc_wage_lookup ON soc_wage_benchmarks(soc_code, oews_year, area_type);
```

### 1.3 Ingestion scripts

Build as a Python CLI using `click` or `typer`. Each data source gets its own command.

```bash
# CLI structure
python ingest.py lca --fiscal-year 2025    # download + parse LCA disclosure data
python ingest.py lca --fiscal-year all     # all available years
python ingest.py violators                  # scrape DOL willful violator list
python ingest.py uscis-hub                  # download USCIS employer data hub
python ingest.py whd-enforcement            # download WHD enforcement data
python ingest.py sos --state NJ             # fetch SOS entity data for state
python ingest.py geocode                    # geocode all employer addresses
python ingest.py classify-addresses         # residential vs commercial classification
```

**Wage normalization logic** (critical — wages come in different units):

```python
def annualize_wage(amount: float, unit: str) -> float:
    """Convert any wage unit to annual equivalent."""
    multipliers = {
        'Year': 1,
        'Month': 12,
        'Bi-Weekly': 26,
        'Week': 52,
        'Hour': 2080,  # 40 hrs/week * 52 weeks
    }
    return amount * multipliers.get(unit, 1)
```

**Employer name normalization** (for matching across data sources):

```python
import re

def normalize_employer_name(name: str) -> str:
    """Normalize employer name for cross-source matching."""
    name = name.upper().strip()
    # Remove common suffixes
    for suffix in [' LLC', ' INC', ' CORP', ' CORPORATION', ' LTD',
                   ' LP', ' LLP', ' CO', ' COMPANY', ' GROUP',
                   ' SERVICES', ' SOLUTIONS', ' TECHNOLOGIES',
                   ',', '.', "'", '"']:
        name = name.replace(suffix, '')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name
```

---

## Phase 2: Anomaly scoring engine

### 2.1 Flag definitions

Each flag has a type, detection logic, and point value. Employer anomaly score = sum of flag scores, capped at 100.

```python
ANOMALY_FLAGS = {
    # --- Industry-job mismatch (detectable from LCA data) ---
    'NAICS_SOC_MISMATCH': {
        'severity': 'CRITICAL',
        'score': 40,
        'description': 'Employer NAICS industry has no plausible connection to filed SOC occupation',
        'detection': '''
            Build a lookup of valid NAICS-SOC pairings from the full LCA dataset.
            For each NAICS code, compute the distribution of SOC codes filed.
            Flag any filing where the NAICS-SOC pair appears in <0.5% of all filings
            for that NAICS code.

            Hard flags (always flag regardless of frequency):
            - NAICS 447xxx (gas stations) + SOC 15-xxxx (computer occupations)
            - NAICS 445xxx (food/beverage retail) + SOC 15-xxxx
            - NAICS 811xxx (repair/maintenance) + SOC 15-xxxx
            - NAICS 453xxx (misc retail) + SOC 15-xxxx
            - NAICS 722xxx (food services) + SOC 15-xxxx (unless large chain HQ)
        '''
    },

    'NON_SPECIALTY_SOC': {
        'severity': 'HIGH',
        'score': 25,
        'description': 'Filed SOC code is not classified as requiring a bachelor\'s degree',
        'detection': '''
            Cross-reference SOC codes against BLS education requirements.
            Flag any H-1B filing where the SOC typical education level is
            "High school diploma" or "Some college, no degree".
            SOC codes to auto-flag: 41-2011, 41-2031, 35-1012, 35-2014,
            53-7065, 43-4051, 43-5081, 37-2011, 39-9011.
        '''
    },

    'WAGE_FAR_BELOW_SOC_MEDIAN': {
        'severity': 'HIGH',
        'score': 25,
        'description': 'Offered wage is <50% of SOC national median',
        'detection': '''
            Compare annualized wage to BLS OES national median for the SOC code.
            Flag if wage < 0.5 * SOC_median.
            Separate threshold for high-cost areas (use MSA-level OES if available).
        '''
    },

    'WAGE_BELOW_PREVAILING': {
        'severity': 'MEDIUM',
        'score': 15,
        'description': 'Offered wage is below DOL prevailing wage for the filing',
        'detection': '''
            Compare annualized wage to annualized prevailing wage from the same LCA.
            Flag if wage_annualized < pw_annualized.
            Note: this should never happen for certified LCAs, but data errors
            and unit mismatches make it appear. Verify units match before flagging.
        '''
    },

    # --- Ghost employer indicators ---
    'RESIDENTIAL_ADDRESS': {
        'severity': 'HIGH',
        'score': 20,
        'description': 'Employer address classified as residential property',
        'detection': '''
            After geocoding, use Google Places API or Smarty/Melissa address
            classification to determine if address is residential.
            Also flag if address matches known apartment/condo patterns
            (contains "APT", "UNIT", "#", "SUITE" in a residential zone).
        '''
    },

    'SHARED_ADDRESS_CLUSTER': {
        'severity': 'HIGH',
        'score': 20,
        'description': '5+ distinct employer names filing from the same address',
        'detection': '''
            Group all employers by normalized address (street + city + state + zip).
            Flag any address with 5+ distinct employer_name_normalized values.
            Exclude known large office buildings / business parks (whitelist).
        '''
    },

    'VIRTUAL_OFFICE': {
        'severity': 'MEDIUM',
        'score': 15,
        'description': 'Address matches known virtual office / mail forwarding provider',
        'detection': '''
            Maintain a list of known virtual office providers:
            Regus, WeWork, Spaces, Servcorp, Davinci, Alliance Virtual,
            iPostal1, PostScanMail, PhysicalAddress.com, The UPS Store, etc.
            Match employer addresses against provider location databases.
        '''
    },

    'NEW_ENTITY_IMMEDIATE_FILING': {
        'severity': 'MEDIUM',
        'score': 15,
        'description': 'Entity formed within 90 days of first LCA filing',
        'detection': '''
            Compare SOS formation_date to first LCA received_date for employer.
            Flag if gap < 90 days.
        '''
    },

    # --- Staffing/placement patterns ---
    'STAFFING_NO_CLIENT': {
        'severity': 'MEDIUM',
        'score': 12,
        'description': 'Staffing/consulting company with no secondary entity listed',
        'detection': '''
            Filter for NAICS 541512 (Computer Systems Design) or 561320
            (Temporary Help Services).
            Flag if SECONDARY_ENTITY_BUSINESS_NAME is null or empty.
        '''
    },

    # --- Filing pattern anomalies ---
    'HIGH_DENIAL_RATE': {
        'severity': 'MEDIUM',
        'score': 12,
        'description': 'Denial rate >2x the average for the same SOC code',
        'detection': '''
            From USCIS employer data hub, compute denial rate per employer.
            Compare to average denial rate for same primary SOC code.
            Flag if employer_denial_rate > 2 * soc_average_denial_rate.
        '''
    },

    'VOLUME_SPIKE': {
        'severity': 'LOW',
        'score': 8,
        'description': 'Filing volume increased >300% year-over-year',
        'detection': '''
            Compare LCA count per employer between consecutive fiscal years.
            Flag if current_year > 3 * prior_year AND prior_year >= 5.
            Exclude first-time filers.
        '''
    },

    'POST_SANCTION_FILING': {
        'severity': 'CRITICAL',
        'score': 35,
        'description': 'Employer or related entity filed LCAs after being sanctioned',
        'detection': '''
            Match violation records to employers.
            Check if any LCA filings exist with received_date > violation_date.
            Also check entity_relationships for sibling entities filing
            after the primary entity was sanctioned.
        '''
    },

    'CONNECTED_TO_VIOLATOR': {
        'severity': 'HIGH',
        'score': 18,
        'description': 'Entity shares address/agent/officer with a known violator',
        'detection': '''
            Traverse entity_relationships graph.
            Flag any employer within 2 hops of a known violator
            (from violations table).
            Weight by relationship type:
            - SHARED_OFFICER: 1.0
            - SHARED_AGENT: 0.8
            - SHARED_ADDRESS: 0.6
            - NAME_VARIANT: 0.9
        '''
    },
}
```

### 2.2 Scoring pipeline

```bash
python score.py run              # score all employers
python score.py run --employer-id 12345  # score single employer
python score.py refresh          # re-score after new data ingestion
python score.py export --min-score 50 --format csv  # export high-risk employers
```

Run scoring after every ingestion. Store individual flags in `anomaly_flags` table. Roll up to `employers.anomaly_score`.

---

## Phase 3: Entity graph builder

### 3.1 Relationship detection

```bash
python graph.py build-address-links     # link employers sharing addresses
python graph.py build-agent-links       # link employers sharing SOS registered agents
python graph.py build-officer-links     # link employers sharing SOS officers
python graph.py build-name-variants     # link employers with similar names (fuzzy match)
python graph.py build-all               # run all
python graph.py visualize --employer-id 12345  # export subgraph as JSON for frontend
```

**Name variant detection** (for entities that rename after enforcement):

```python
from rapidfuzz import fuzz

def find_name_variants(employers: list, threshold: float = 85.0):
    """Find employer name pairs that are likely variants of each other."""
    variants = []
    for i, emp_a in enumerate(employers):
        for emp_b in employers[i+1:]:
            score = fuzz.token_sort_ratio(
                emp_a['name_normalized'],
                emp_b['name_normalized']
            )
            if score >= threshold:
                # Additional check: same state or same city
                if (emp_a['state'] == emp_b['state'] or
                    emp_a['city'] == emp_b['city']):
                    variants.append({
                        'employer_a': emp_a['id'],
                        'employer_b': emp_b['id'],
                        'similarity': score / 100.0,
                        'type': 'NAME_VARIANT'
                    })
    return variants
```

### 3.2 Graph queries

Store in PostgreSQL with JSONB for flexibility. If graph traversal performance becomes an issue, migrate to Neo4j.

Key queries the frontend will need:

```sql
-- Find all entities connected to a violator within 2 hops
WITH RECURSIVE connected AS (
  SELECT employer_id_b AS eid, 1 AS depth
  FROM entity_relationships
  WHERE employer_id_a = :violator_id
  UNION
  SELECT er.employer_id_b, c.depth + 1
  FROM entity_relationships er
  JOIN connected c ON er.employer_id_a = c.eid
  WHERE c.depth < 2
)
SELECT DISTINCT e.*, c.depth
FROM employers e
JOIN connected c ON e.id = c.eid;

-- Find all entities at the same address
SELECT e.*
FROM employers e
WHERE e.address_line1 = :address
  AND e.city = :city
  AND e.state = :state;

-- Find entities sharing a registered agent
SELECT e.*, se.registered_agent
FROM employers e
JOIN sos_entities se ON e.id = se.employer_id
WHERE se.registered_agent ILIKE :agent_name;
```

---

## Phase 4: Web dashboard

### 4.1 Tech stack

- **Framework**: Next.js 14+ (App Router)
- **Database access**: Prisma ORM
- **Styling**: Tailwind CSS
- **Charts**: Recharts or D3
- **Graph visualization**: d3-force or cytoscape.js
- **Map**: Mapbox GL or Leaflet
- **Deployment**: Vercel or Railway
- **API**: Next.js API routes (rate-limited with upstash/ratelimit)

### 4.2 Pages and routes

```
/                           — landing page with stats + top flagged employers
/search                     — full-text employer search
/employer/[id]              — employer profile page
  - filing history (LCA table with trend charts)
  - anomaly flags with explanations
  - entity relationship graph
  - violation history timeline
  - wage distribution vs SOC median
  - address verification status
/address/[hash]             — all entities at a given address
/map                        — geographic heatmap of anomaly density
/violators                  — DOL violator list enriched with filing activity
/graph/[id]                 — interactive entity relationship explorer
/tip/[employer_id]          — tip generator (pre-filled complaint forms)
/api/v1/employer/[ein]      — public API
/api/v1/anomalies           — filtered anomaly feed
/api/v1/address/[hash]      — entities at address
```

### 4.3 Employer profile page (key view)

The employer profile is the core UX. It should answer: "Is this employer legitimate, and if not, what specifically is wrong?"

Sections:
1. **Header**: employer name, address, NAICS industry, anomaly score badge, active/debarred status
2. **Anomaly flags**: each flag with severity, explanation, and the specific data that triggered it
3. **Filing history**: table of all LCA filings sortable by date, SOC, wage, status. Sparkline of filing volume over time.
4. **Wage analysis**: offered wages vs prevailing wage vs SOC national median. Box plot or violin chart.
5. **Entity graph**: interactive force-directed graph showing connected entities. Violators highlighted red.
6. **Violation history**: timeline of enforcement actions with outcomes.
7. **Address verification**: map showing employer location, address type classification, other entities at the same address.
8. **Tip button**: generates pre-formatted complaint for DOL or USCIS.

---

## Phase 5: Tip generator

### 5.1 Legal basis

Under 20 CFR § 655.805, any "interested party" can file an LCA complaint with DOL. The complaint must allege specific violations of the attestation requirements. The tool pre-fills complaints based on detected anomalies.

### 5.2 Complaint templates

**DOL Form WH-4 (LCA complaint)**
```
Pre-fill fields:
- Employer name (from LCA data)
- Employer address (from LCA data)
- Violation type (mapped from anomaly flags):
  - "Wage below prevailing" → LCA wage violation
  - "NAICS-SOC mismatch" → Misrepresentation of job duties
  - "No client worksite" → Worksite location violation
- Supporting data points (from analysis):
  - "Employer filed SOC 15-1252 (Software Developers) but operates as
     NAICS 447110 (Gasoline Stations with Convenience Stores)"
  - "Offered wage of $31,000 is 76% below the SOC national median of $127,260"
  - "12 other entities file LCAs from the same address at [address]"
```

**USCIS tip form content**
```
Pre-generate narrative:
- Employer identification
- Specific suspected violations
- Supporting public data evidence
- Entity relationship context (if connected to known violators)
```

### 5.3 Evidence package

For each flagged employer, generate a downloadable PDF evidence package containing:
- Employer profile summary
- All anomaly flags with supporting data
- LCA filing history table
- Entity relationship diagram
- Address verification results
- Comparison to peer employers in same NAICS/SOC
- Links to source data (DOL disclosure files, USCIS hub)

---

## Phase 6: Integration with visadata.org

### 6.1 Complementary positioning

visadata.org (H1B Verification System / fraudreporter.visadata.org) focuses on physical address verification through community site visits. This tool focuses on data analysis and entity relationships. Together they cover the full picture.

### 6.2 Integration points

- **Inbound**: consume visadata.org's verified/unverified address status for employer addresses. If they publish an API or data export, ingest it. Their green/red marker status adds a ground-truth layer to the address classification.
- **Outbound**: surface our entity graph and anomaly analysis as context for their site visit prioritization. A "visit this address" with context that "14 shell companies file from this suite and 3 are connected to a debarred employer" is more actionable than a bare pin on a map.
- **Shared tip pipeline**: both tools ultimately feed the same DOL/USCIS complaint channels. Coordinate on evidence format so site visit photos + data analysis compose into a single complaint package.

### 6.3 Implementation

Start by linking to visadata.org from employer profile pages. Reach out to their team about data sharing or API access. If they're open to it, build a bidirectional data feed. If not, maintain independent address verification and link to their map for the physical verification layer.

---

## Phase 7: AutoResearch investigation framework

### 7.1 Concept

The batch scoring pipeline (Phases 1-3) flags employers at scale — 30K+ employers scored, thousands flagged. But a flag is not an investigation. The AutoResearch pattern converts a flagged employer into a structured, multi-source deep-dive that produces a narrative investigation report — the same pattern used in the land sourcing tool (`land_site_selection_program.md`) but applied to employer investigations instead of parcels.

The batch pipeline answers: "Which employers look suspicious?"
The AutoResearch pipeline answers: "Here's everything we know about this specific employer, assembled from every available source, in a format ready to submit to DOL."

### 7.2 Architecture mapping

```
Land Sourcing (existing)          →  Employer Investigation (new)
─────────────────────────────────────────────────────────────────
Research target: parcel           →  Research target: flagged employer
County connectors (tax, zoning)   →  Data connectors (DOL, USCIS, OpenCorporates, Smarty, SOS)
Investment Thesis narrative       →  Investigation Report narrative
Acquisition strategies            →  Violation type classification
actionable_pipeline_count metric  →  anomaly_score + flag breakdown
Loosened entitlement gate         →  Score threshold for deep-dive trigger (score >= 40)
```

### 7.3 Investigation connector spec

Each connector pulls data for a single employer and returns structured output.

```python
# Connector interface
class InvestigationConnector:
    def fetch(self, employer_id: int) -> dict:
        """Fetch all available data for this employer from one source."""
        raise NotImplementedError

# Connectors to implement:

class LCAHistoryConnector(InvestigationConnector):
    """Pull full LCA filing history from local database.
    Returns: all filings, wage trends, SOC distribution, status breakdown,
    secondary entities (client companies), worksite locations."""

class USCISApprovalConnector(InvestigationConnector):
    """Pull USCIS approval/denial history from local database.
    Returns: approval rates by year, initial vs continuing, denial trends."""

class EnforcementConnector(InvestigationConnector):
    """Pull WHD enforcement actions and willful violator status.
    Returns: violations, back wages, penalties, debarment dates."""

class WageBenchmarkConnector(InvestigationConnector):
    """Compare employer's wages against BLS OEWS benchmarks.
    Returns: wage vs SOC median at national and MSA level,
    percentile position, peer comparison."""

class EntityGraphConnector(InvestigationConnector):
    """Traverse entity relationships from local graph.
    Returns: connected entities, relationship types, degrees of separation
    from known violators, shared addresses/agents/officers."""

class OpenCorporatesConnector(InvestigationConnector):
    """Fetch corporate registration details.
    Returns: formation date, status, registered agent, officers,
    filing history, jurisdiction."""

class AddressVerificationConnector(InvestigationConnector):
    """Classify and verify employer address.
    Returns: residential/commercial/virtual classification,
    geocoded coordinates, other entities at same address,
    visadata.org verification status (if integrated)."""

class PublicWebPresenceConnector(InvestigationConnector):
    """Check for employer's web presence (Phase 2).
    Returns: website exists (Y/N), domain age, LinkedIn company page,
    BBB listing, Google Maps listing with reviews."""
```

### 7.4 Investigation report output

The AutoResearch pipeline assembles connector outputs into a structured Investigation Report — formatted as copy-paste text for the tip generator.

```
EMPLOYER INVESTIGATION REPORT
═══════════════════════════════════════════════════════════════

Target: SUNRISE CONVENIENCE LLC
EIN (last 4): **7842
Address: 1234 Memorial Dr, Decatur, GA 30032
NAICS: 447110 (Gasoline Stations with Convenience Stores)
Anomaly Score: 85 / 100 (CRITICAL)

─── ANOMALY FLAGS ─────────────────────────────────────────────

[CRITICAL] INDUSTRY_JOB_MISMATCH (40 pts)
  Gas station employer filed for SOC 15-1252 (Software Developers).
  This NAICS-SOC pairing appears in <0.1% of all H-1B filings nationally.

[HIGH] WAGE_FAR_BELOW_SOC_MEDIAN (25 pts)
  Offered wage: $31,200/yr
  SOC 15-1252 national median: $127,260/yr
  Wage is 75.5% below national median for claimed occupation.

[HIGH] RESIDENTIAL_ADDRESS (20 pts)
  Employer address classified as residential property (Smarty DPV indicator).
  3 other entities file H-1B LCAs from this same address.

─── FILING HISTORY ────────────────────────────────────────────

Total LCAs filed: 14 (FY2022-FY2025)
Case outcomes: 9 CERTIFIED, 3 DENIED, 2 WITHDRAWN
SOC codes used: 15-1252 (11), 11-1021 (2), 41-2011 (1)
Wage range: $28,000 - $38,000 (all well below prevailing wage)

─── USCIS PETITION OUTCOMES ───────────────────────────────────

Initial approvals: 4 | Initial denials: 7 | Denial rate: 63.6%
Industry average denial rate for SOC 15-1252: 8.2%
Employer denial rate is 7.8x the industry average.

─── ENTITY RELATIONSHIPS ──────────────────────────────────────

Connected entities at same address:
  - GALAXY GAS & FOOD LLC (anomaly score: 72)
  - QUICK STOP PETROLEUM INC (anomaly score: 68)
Shared registered agent: [Agent Name] also represents:
  - 4 other entities with combined anomaly score avg: 61

─── WAGE BENCHMARK ANALYSIS ───────────────────────────────────

                    Employer    National Median    Employer Percentile
Software Dev        $31,200     $127,260           <1st percentile
Gen Mgr             $34,000     $97,970            <5th percentile

─── ADDRESS VERIFICATION ──────────────────────────────────────

Classification: RESIDENTIAL
Coordinates: 33.7751, -84.2963
Other filers at address: 3 entities
visadata.org status: NOT YET VERIFIED (red marker)

─── RECOMMENDED ACTION ────────────────────────────────────────

File LCA complaint with DOL Wage and Hour Division citing:
  1. Misrepresentation of job duties (NAICS-SOC mismatch)
  2. Wage below prevailing wage for occupation and area
  3. Questionable business presence at stated address

Copy-paste text for DOL complaint form and USCIS tip form
generated below.
```

### 7.5 Pipeline trigger

```bash
# Investigate a single employer
python investigate.py --employer-id 12345

# Batch investigate all employers above score threshold
python investigate.py --min-score 40

# Generate tip-ready text for a specific employer
python investigate.py --employer-id 12345 --output tip

# Export investigation report as formatted text file
python investigate.py --employer-id 12345 --output report --format txt
```

### 7.6 Implementation sprint

This is Sprint 5 work (Week 6), after the web dashboard is functional. The connectors mostly query the local database (already populated by Sprints 1-3). Only OpenCorporates and address verification connectors make external API calls, and those results are cached in the database from Sprint 3.

---

## Implementation order for Claude Code

### Sprint 1: Data pipeline (Week 1)

```
Task 1.0: Prototype with Kaggle data (Day 1)
  - Download a pre-cleaned Kaggle H-1B LCA dataset for rapid iteration
  - Use it to validate schema, test wage normalization, and build
    employer deduplication logic before touching raw DOL files
  - Throw away the Kaggle data once the pipeline works

Task 1.1: Set up project scaffolding
  - Python project with pyproject.toml
  - PostgreSQL via Docker Compose
  - Alembic for migrations
  - Create all tables from schema above

Task 1.2: LCA disclosure data ingestion
  - Download OFLC Excel/CSV files from dol.gov/agencies/eta/foreign-labor/performance
  - Get FY2020-FY2025 full year files (6 files)
  - Parse and normalize (wage annualization, employer name normalization)
  - Handle column name variations across fiscal years (check record layouts)
  - Deduplicate employers by normalized name + state
  - Load into lca_filings and employers tables
  - Estimated: ~4.5M+ records across 6 fiscal years

Task 1.3: USCIS employer data hub ingestion
  - Download CSV files from uscis.gov/archive/h-1b-employer-data-hub-files
  - Get FY2020-FY2025 annual files
  - Match to employers by normalized name + state + ZIP
  - Store approval/denial rates (initial + continuing, separate columns)
  - Note: USCIS identifies employers by last 4 of tax ID — use as secondary match key

Task 1.4: BLS OEWS wage data ingestion
  - Download national_M2024_dl.xlsx from bls.gov/oes/tables.htm
  - Download MSA-level file for Phase 2
  - Parse into soc_wage_benchmarks table
  - Key columns: SOC code, median annual wage, mean annual wage, percentiles
  - This is the benchmark dataset for wage anomaly detection

Task 1.5: DOL enforcement data ingestion
  - Download WHD enforcement CSV from enforcedata.dol.gov
  - Filter for H-1B/LCA/INA violation types
  - Load into violations table
  - Match to employers by normalized name + city + state

Task 1.6: DOL willful violator list ingestion
  - Scrape HTML table from dol.gov/agencies/whd/immigration/h1b/willful-violator-list
  - Parse into violations table with source = 'DOL_WILLFUL'
  - Match to employers by normalized name

Task 1.7: Set up incremental update pipeline
  - Configure DOL Data Portal API (apiprod.dol.gov/v4/) for WHD delta queries
  - No API key needed
  - Build cron job stub for quarterly LCA file checks
```

### Sprint 2: Analysis engine (Week 2)

```
Task 2.1: Build NAICS-SOC mismatch detector
  - Compute NAICS-SOC frequency distribution from full LCA dataset
  - Implement hard-flag rules for obvious mismatches
  - Implement statistical flagging for rare pairings (<0.5% frequency)

Task 2.2: Build wage anomaly detector
  - Load BLS OEWS data (ingested in Sprint 1, Task 1.4)
  - Compare annualized LCA wages to SOC national medians
  - Flag if wage < 50% of SOC median (WAGE_FAR_BELOW_SOC_MEDIAN)
  - Flag if wage < annualized prevailing wage (WAGE_BELOW_PREVAILING)
  - Phase 2: Use MSA-level OEWS medians for location-adjusted comparisons

Task 2.3: Build address classifier
  - Batch geocode all employer addresses with Nominatim (free, ~8hrs for 30K)
  - Store lat/lng in employers table
  - Classify using Smarty dpv_residential_delivery_indicator (~$300 for 30K)
    OR build virtual office provider address list and match against it (free)
  - Detect shared address clusters (GROUP BY normalized address, flag 5+ employers)
  - Match against known virtual office providers (Regus, WeWork, UPS Store, etc.)

Task 2.4: Build filing pattern analyzer
  - Compute denial rates per employer from USCIS hub data
  - Compare to SOC-code-level average denial rates
  - Detect volume spikes (>300% YoY increase)
  - Detect post-sanction filing activity (LCA filings after violation date)

Task 2.5: Implement scoring pipeline
  - Run all detectors
  - Store individual flags in anomaly_flags table
  - Roll up to employer anomaly_score (sum of flag scores, capped at 100)
  - Export: `python score.py export --min-score 50 --format csv`
```

### Sprint 3: Entity graph (Week 3)

```
Task 3.1: Address-based entity linking
  - Link employers sharing normalized addresses
  - Use shared address clusters from Sprint 2 Task 2.3
  - Store in entity_relationships with type = 'SHARED_ADDRESS'

Task 3.2: Name variant detection
  - Fuzzy match employer names within same state using rapidfuzz
  - Token sort ratio threshold >= 85%
  - Detect post-enforcement name changes (violator name ≈ new filer name)
  - Store with type = 'NAME_VARIANT'

Task 3.3: OpenCorporates entity enrichment
  - Apply for free public-benefit API key at opencorporates.com
  - Batch reconcile employer names against OpenCorporates using Open Refine
    reconciliation endpoint (most efficient for bulk matching)
  - For matched entities, pull:
    - Formation date (flag if entity formed <90 days before first LCA)
    - Registered agent name
    - Officers/directors
    - Entity status (active/dissolved/revoked)
  - Store in sos_entities table
  - Link employers sharing registered agents (type = 'SHARED_AGENT')
  - Link employers sharing officers (type = 'SHARED_OFFICER')

Task 3.4: Direct state registry supplement (FL + TX only)
  - FL Sunbiz: free search + scanned docs, officers available
  - TX Comptroller: bulk entity data on open data portal
  - Only for employers where OpenCorporates data is missing or incomplete
  - Priority: employers already flagged with anomaly_score >= 25

Task 3.5: Violator network mapping
  - Traverse entity_relationships graph from known violators
  - Flag entities within 2 hops (recursive CTE)
  - Weight by relationship type (SHARED_OFFICER: 1.0, SHARED_AGENT: 0.8,
    SHARED_ADDRESS: 0.6, NAME_VARIANT: 0.9)
  - Store connected-to-violator flags in anomaly_flags
```

### Sprint 4: Web dashboard (Weeks 4-5)

```
Task 4.1: Next.js project setup
  - App Router, Prisma, Tailwind
  - Database connection to existing PostgreSQL

Task 4.2: Search and listing pages
  - Full-text employer search
  - Filterable anomaly feed
  - Violator list with enriched data

Task 4.3: Employer profile page
  - All sections described in 4.3 above
  - Interactive charts for wage analysis
  - Entity graph visualization

Task 4.4: Map view
  - Geographic heatmap of anomaly density
  - Clickable markers for flagged employers

Task 4.5: Tip generator
  - Pre-filled complaint forms
  - Evidence package PDF generation
  - Links to DOL and USCIS submission portals

Task 4.6: Public API
  - Rate-limited REST endpoints (no auth, rate limiting only)
  - Endpoints: /employer/{ein}, /address/{hash}, /anomalies
```

### Sprint 5: AutoResearch investigation pipeline (Week 6)

```
Task 5.1: Build connector framework
  - Base InvestigationConnector class
  - LCAHistoryConnector (queries local database)
  - USCISApprovalConnector (queries local database)
  - EnforcementConnector (queries local database)
  - WageBenchmarkConnector (joins soc_wage_benchmarks)
  - EntityGraphConnector (recursive CTE traversal)
  - AddressVerificationConnector (reads cached Smarty results)

Task 5.2: OpenCorporates connector
  - Queries OpenCorporates API for employer entity details
  - Caches results in sos_entities table
  - Rate-limit aware (respect free tier limits)

Task 5.3: Investigation report generator
  - Assembles all connector outputs into structured report
  - Formats as copy-paste text for DOL complaint form
  - Formats as copy-paste text for USCIS tip form
  - CLI: python investigate.py --employer-id 12345

Task 5.4: Batch investigation mode
  - python investigate.py --min-score 40
  - Runs deep-dive on all employers above threshold
  - Outputs investigation reports to /reports directory

Task 5.5: Integration with web dashboard
  - "Generate Investigation Report" button on employer profile page
  - "Copy Tip Text" button that formats for DOL/USCIS forms
  - Report viewer on employer profile page
```

---

## Key technical decisions

**PostgreSQL over Neo4j** for entity graph — start with PostgreSQL + recursive CTEs. The graph is sparse (most employers have 0-2 connections) and the queries are simple (find connected within N hops). Neo4j adds operational complexity for no gain until the graph has 100K+ edges.

**Python for data pipeline, TypeScript for web** — LCA files are messy CSVs that benefit from pandas. The web layer is a standard Next.js app. Don't force one language to do both.

**Kaggle for prototyping, DOL for production** — Start Sprint 1 with a pre-cleaned Kaggle dataset to validate the schema and normalization logic. Switch to direct DOL downloads once the pipeline works. This saves a day of fighting Excel column name variations during initial development.

**OpenCorporates over direct state registries** — State SOS data accessibility ranges from excellent (Florida, Texas) to effectively paywalled (Delaware, New Jersey). OpenCorporates aggregates 145 jurisdictions with consistent API access and data provenance. Start there, supplement with direct FL Sunbiz and TX Comptroller for high-priority gaps. Going direct to 50 state registries is an engineering tar pit — OpenCorporates exists specifically to solve this problem.

**Smarty over Google for address classification** — Smarty's `dpv_residential_delivery_indicator` directly answers "is this a residence or a business?" for ~$0.01/lookup. Google Geocoding gives you lat/lng but requires a second Places API call ($0.017/call) to infer building type indirectly. Use Nominatim (free) for geocoding coordinates, Smarty for the classification. Total cost: ~$300 one-time for 30K addresses.

**BLS OEWS for wage benchmarking** — Downloaded from `bls.gov/oes/tables.htm`. May 2024 is latest. Uses same 2018 SOC codes as DOL LCA data — no crosswalk needed. National medians for Phase 1, MSA-level medians for Phase 2 location-adjusted scoring. Annual release, ~830 occupations.

**DOL Data Portal API for incremental updates** — No API key required. REST endpoint at `apiprod.dol.gov/v4/`. Use for WHD enforcement delta queries between quarterly bulk file downloads. Bulk files remain the primary ingestion path.

**visadata.org as integration partner, not data source** — They have no public API. Their value is physical address verification (crowdsourced site visits with photos). Reach out for data sharing. In the meantime, link to their map from employer profile pages and build independent address classification using Smarty + virtual office provider matching.

---

## Legal considerations

- All primary data sources are public records published by federal agencies. No FOIA required.
- 20 CFR § 655.805 explicitly grants standing to "interested parties" to file LCA complaints.
- DOL LCA disclosure data is published specifically for public transparency per DOL open government policy.
- USCIS employer data hub is public and explicitly designed for external analysis.
- DOL enforcement data is public via enforcedata.dol.gov and the DOL Data Portal API.
- BLS OEWS wage data is public domain (US government work product, no license restrictions).
- State SOS data is public record in all 50 states (access mechanisms and fees vary).
- OpenCorporates data: free for open data / public benefit projects under share-alike attribution license. Confirm your project qualifies before bulk API usage.
- h1bgrader.com ToS: explicitly prohibits using their content as "a source of or substitute for the Service" or in ways that "compete with the Service." Do not scrape. Use the same underlying DOL/USCIS sources directly instead.
- Do not store or display individual worker (beneficiary) names — they appear in some LCA fields but are PII and not needed for employer-level analysis.
- Smarty/geocoding API ToS: review their terms for caching and redistribution of address classification results. Most providers allow caching for your own use.
- Framing matters: "H-1B transparency and accountability" not "H-1B fraud tracker." The tool surfaces anomalies in public data; it does not make fraud determinations. Let enforcement agencies make those determinations using the evidence packages you generate.

---

## Success metrics

- Number of unique employer profiles viewed
- Number of tip packages generated
- Number of formal complaints filed using tool-generated evidence (if trackable)
- Coverage: % of DOL LCA filings analyzed
- Accuracy: % of flagged employers that have subsequent enforcement action (lagging indicator)
- Press citations / policy references

---

## Open questions for build phase

### Resolved from research
1. ~~Entity graph DB?~~ → PostgreSQL with recursive CTEs. Migrate to Neo4j only if graph exceeds 100K edges.
2. ~~Geocoding provider?~~ → Nominatim (free) for lat/lng, Smarty (~$300) for residential/commercial classification. Cache aggressively.
3. ~~visadata.org API?~~ → No public API exists. Outreach required for data sharing. Build independent address classification in parallel.
4. ~~State SOS data access?~~ → OpenCorporates API (free for public benefit) as primary aggregator. FL Sunbiz and TX Comptroller as direct supplements.
5. ~~BLS wage data format?~~ → Excel downloads from bls.gov/oes/tables.htm. Uses same 2018 SOC codes as LCA data. No crosswalk needed.
6. ~~DOL API auth?~~ → No API key required for DOL Data Portal API. REST endpoint at apiprod.dol.gov/v4/.

### Resolved by Andrey
1. ~~Tip generator format?~~ → Formatted text for copy-paste into the DOL online form. No fillable PDF generation needed.
2. ~~Public API auth?~~ → Rate limiting only, no auth. Start fully open.
3. ~~Hosting?~~ → Railway or Render. Need flexibility for background jobs, cron-based ingestion, and long-running scoring pipelines.
4. ~~OpenCorporates tier?~~ → Use free tier for now. Negotiate higher tier only if rate limits become a bottleneck during batch reconciliation.
5. ~~BLS OEWS storage?~~ → Separate `soc_wage_benchmarks` table for accuracy. Preload BLS data once, join at query time. This keeps wage benchmarks versioned independently from LCA data and avoids re-downloading BLS data on every scoring run.
6. ~~LCA column normalization?~~ → Use Kaggle pre-cleaned dataset as the canonical field list. Map raw DOL column names to the Kaggle schema during ingestion. This avoids reinventing the normalization that Kaggle contributors already solved.

### All open items resolved. Spec is ready for Claude Code implementation.
