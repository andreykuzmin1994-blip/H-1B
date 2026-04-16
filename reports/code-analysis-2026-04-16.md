# H-1B Transparency Engine — Code Analysis Report

**Date:** 2026-04-16
**Branch:** `claude/code-analysis-review-JirY5`
**Method:** Three parallel Explore-agent passes (security, scalability/tech-debt, redundancy), then cross-checked for contradictions.

---

## TL;DR

The codebase is reasonably well-structured (clean dependency tree, parameterized SQLAlchemy, batched LCA ingest, no `eval`/`pickle`/`shell=True`), but it has three compounding problems:

1. **Production readiness is blocked by infrastructure basics** — default DB credentials, exposed DB port, wildcard CORS, zero API auth, missing security headers. Fast to fix, urgent.
2. **Scale assumptions don't match the data volume** — no job queue, full in-memory aggregations during scoring, O(n²) pairwise graph link building, table-locking migrations, no retry/backoff on external APIs (despite `tenacity` being in `pyproject.toml`).
3. **~700 lines of model code and 6 tables have no data producer** — the personnel/credentials/university/registration pipeline is wired end-to-end *except* for ingestion. The user's instinct about "code going nowhere" is correct and quantifiable.

No hard contradictions between the three analyses. Several findings *overlap* — flagged below, since fixing them kills two birds.

---

## 1. Security

### Must-fix before any public deployment
| Severity | Finding | Location |
|---|---|---|
| CRITICAL | Default PostgreSQL creds (`h1b` / `h1b`) in compose file | `docker/docker-compose.yml:9-10` |
| CRITICAL | Postgres port `5432:5432` exposed on host (should bind to `127.0.0.1` or be removed) | `docker/docker-compose.yml:11-12` |
| HIGH | Server Actions `allowedOrigins: ['*']` — CSRF wide open | `frontend/next.config.js:4` |
| HIGH | No auth on any `/api/v1/*` endpoint (only rate-limit) | `frontend/app/api/v1/{graph,employer,anomalies,address}/...` |
| HIGH | No CSP / HSTS / X-Frame-Options / X-Content-Type-Options | `frontend/next.config.js` (absent) |

### Medium
- `prisma.$queryRawUnsafe` in graph route — inputs *are* validated (`Number.isFinite`, depth ≤ 3), not exploitable today, but switch to `$queryRaw` to remove the footgun. `frontend/app/api/v1/graph/[id]/route.ts:16`
- Rate-limit falls back to in-memory `Map` without Upstash — resets on restart, unbounded growth. `frontend/lib/ratelimit.ts:4-26`
- Employer endpoint returns 50 filings + flags + violations with no auth/pagination — bulk-scrape surface. `frontend/app/api/v1/employer/[ein]/route.ts:26-29`

### Positives (confirmed clean)
- All SQLAlchemy uses the `select()` DSL — no string concatenation.
- No `pickle`, `yaml.unsafe_load`, `eval`, `exec`, `os.system`, or `shell=True`.
- All ingestor URLs are hardcoded (no user-controlled URL → no SSRF vector).
- API secrets read from `os.environ`; no hardcoded keys.

---

## 2. Scalability & Technical Debt

### High impact
- **No job queue.** Ingest, scoring, and graph-build are synchronous CLI-only. No Celery/RQ/Arq. Any future "re-score" HTTP trigger would time out. `score/engine.py:31-84`, `ingest/lca.py:239-296`.
- **Full in-memory aggregations in scoring.** `score_all()` precomputes NAICS×SOC frequency, address clusters, and national SOC medians *before* scoring any employer. At O(10M) LCA rows, these dicts go multi-GB. `score/engine.py:34-44`.
- **O(n²) pairwise graph builds.** `graph/builder.py:51-175` loads all rows, buckets in Python, then `combinations(ids, 2)`. 1000 employers at one address = 500k edges.
- **Table-locking migration.** `migrations/versions/0002_jsonb_and_partial_index.py` does `ALTER COLUMN TYPE JSONB` — `ACCESS EXCLUSIVE` on the whole table. Also no `CREATE INDEX CONCURRENTLY` anywhere.
- **No retry/backoff on external APIs** despite `tenacity>=8.2` being a declared dependency that is never imported. `ingest/opencorporates.py:45,62,87`, `ingest/geocode.py:71-76`.
- **Missing indexes on `LcaFiling`** for common filter combos: `wage_ratio`, `case_status`, `(employer_id, fiscal_year)`, `(case_status, received_date)`. `db/models.py:62-99`.

### Medium
- CSV ingest likely loads the whole file via pandas before chunked insert — OOM risk on full DOL LCA dumps. `ingest/lca.py`, `ingest/warn.py`.
- Frontend pages `findMany({ take: 1000 })` without cursor pagination. `frontend/app/map/page.tsx:10-15`, `frontend/app/api/v1/anomalies/route.ts:22-27`.
- Test coverage gap: `lca.py`, `geocode.py`, `opencorporates.py`, `warn.py` have no dedicated tests; only normalization is covered.

### Low
- Magic numbers in `score/flags.py` and `score/detectors.py` (threshold=5, flag weights 40/25/20/15) with no constants or docstrings.
- `DATA_DIR` defaults to relative `./data` — breaks in containers. `ingest/common.py:16-21`.
- Virtual-office keywords hardcoded rather than a lookup table. `ingest/geocode.py:23-43`.

### Positives
- No circular imports across 36 modules. Single `get_session()` entry point.
- LCA ingest uses `batch_size=1000` with idempotent `case_number` dedupe.
- PostgreSQL subgraph traversal uses a recursive CTE (the Python fallback is the slow path).

---

## 3. Redundancy / Dead Code

### Confirmed dead (~700 lines + 6 tables)
1. **Personnel/credentials pipeline has no producer.** `Beneficiary`, `University`, `UniversityProgram`, `UniversitySignatory`, `CredentialClaim`, `H1BRegistration`, `CredentialEvaluator` — defined in `db/models.py:316-670`, created by `migrations/0004_personnel_credentials.py`, *consumed* by `credentials/lookup.py` + `credentials/detectors.py`, but nothing in `ingest/` populates them. Only manual CLI seeding exists.
2. **Attorney fields on `LcaFiling`** (`attorney_name`, `attorney_name_normalized`, `attorney_firm`) defined in `db/models.py:76-80`, indexed (`idx_lca_attorney_name_norm`), used by a detector at `detectors.py:813-815`. But `ingest/lca.py` never extracts attorney fields from the DOL source — always NULL in practice.
3. **`PublicWebPresenceConnector`** — stub that always returns `{"available": False, "reason": "not_implemented"}`. `investigate/connectors.py:252-261`, called from `report.py` via `fetch_all()` at `connectors.py:441`.

### Likely dead (~70-90% confidence)
- `EmployerPayrollRecord` model + `NO_PAYROLL_FOR_H1B_VOLUME` detector — no ingestion path; detector only fires if the table has data. `db/models.py:613-641`, `detectors.py:704-759`.
- `KnownFraudDefendant`, `DisciplinedPractitioner` reference tables — only populated by `score/reference.py:bootstrap_score_reference()`, which is never called in production. `db/models.py:561-610`.

### Minor duplication
- Wage annualization logic repeated in `ingest/lca.py:258-260` rather than using the canonical `utils/wages.py:27:annualize_wage()`.
- `utils/names.py:64:normalize_address` has only one caller — fold into the general normalizer.
- Each ingestor rolls its own `requests.get` pattern; a shared HTTP client with `tenacity` retry would consolidate this *and* fix the scalability gap.

### Not dead (verified)
- **All frontend components are imported.** Every file in `frontend/components/` has a consumer in `app/`. No UI dead weight.
- Migrations 0001-0003 are foundational. 0004-0005 create stubs for #1-#2 above.

---

## 4. Cross-Agent Cross-Check — Contradictions & Overlaps

**No direct contradictions.** The three analyses are complementary. Notable overlaps where a single fix resolves findings in multiple reports:

| Overlap | Security says | Scalability says | Redundancy says |
|---|---|---|---|
| **Credentials/personnel module** | "Unused module, unknown integration status — MEDIUM attack surface" | — | "Confirmed dead: 6 tables, ~450 lines, no producer" |
| **Attorney LCA fields** | — | "Unused index wastes write throughput" | "Confirmed dead: never populated" |
| **`tenacity` dependency** | "Dependencies modern & patched" (positive) | "Declared but never imported → no retry/backoff" | — |
| **Pagination on employer/anomalies** | "Info disclosure — bulk scrape surface" | "No cursor pagination; `take: 500/1000` hardcoded" | — |
| **Rate limiting** | "In-memory fallback resets on restart" | "No Redis caching anywhere" | — |

### Reconciled positions
- **Credentials module**: security flagged it as unknown-state risk; redundancy confirmed it is dead. **Resolution: delete it.** That eliminates both the attack surface and the dead code. If the personnel pipeline is still roadmap, keep the migrations but gate behind a feature flag.
- **`tenacity`**: security's "dependencies are modern" is correct as a CVE statement; scalability's "never imported" is correct as a utilization statement. Both true — install is safe, usage is absent.
- **Pagination**: one fix (cursor-based pagination with a server-enforced cap) closes both the scrape-surface concern and the throughput concern.

### Gap that no agent fully owned
- **Observability**: no structured logging config, no metrics endpoint, no trace IDs on API routes. This straddles all three concerns (security audit trail, scale debugging, redundant ad-hoc logging).

---

## 5. Recommended Sequencing

**Week 1 — unblock deployment (security + quick wins)**
1. Rotate Postgres creds; move to env-only; bind `127.0.0.1:5432` (or remove host mapping entirely). `docker/docker-compose.yml`
2. Set `allowedOrigins` to the actual frontend origin. `frontend/next.config.js`
3. Add security headers (CSP, HSTS, XFO, XCTO) via Next.js `headers()` config.
4. Decide: public API (document it) vs. authenticated (add middleware). `frontend/app/api/v1/**`
5. Swap `$queryRawUnsafe` → `$queryRaw`. `frontend/app/api/v1/graph/[id]/route.ts:16`

**Week 2 — kill dead code**
6. Delete `PublicWebPresenceConnector` stub.
7. Either wire LCA attorney extraction or drop the 3 columns + index + detector branch.
8. Decide fate of personnel/credentials stack (delete or gate + roadmap). If kept, add the ingest module; if dropped, revert migrations 0004-0005.

**Week 3-4 — scale prep**
9. Introduce a shared HTTP client using `tenacity` with exponential backoff.
10. Add missing `LcaFiling` indexes via `CREATE INDEX CONCURRENTLY` migration.
11. Add cursor pagination to `anomalies`, `map`, `employer` endpoints.
12. Convert full-dataset scoring aggregations to chunked/streaming (or persist to a materialized view).
13. Replace the `combinations(ids, 2)` graph build with batched SQL that writes edges directly, capped per-bucket.
14. Introduce a job queue (Arq pairs nicely with the FastAPI/async stack). Move `score_all` and heavy ingest off the request path.

**Ongoing**
15. Backfill tests for `lca.py`, `opencorporates.py`, `geocode.py`, `warn.py`, and the graph builder at scale.
16. Replace magic numbers with a typed settings module (pydantic-settings).

---

## 6. Scope & Confidence Notes

- Each agent searched the full tree (`backend/h1b_engine/`, `frontend/`, `docker/`, migrations, tests) independently.
- All findings cite `file:line`. Where agents labeled something "LIKELY DEAD" vs "CONFIRMED DEAD," that distinction reflects whether the call graph was fully verified or relied on grep-for-callers.
- The redundancy report's claim that "all frontend components are imported" was verified by agent-side import tracing but not exhaustively by this synthesis — treat as high confidence, not proven.
- This report does not perform dynamic analysis (no running the code). A few scalability claims (e.g., "CSV likely loaded into memory") are structural inferences from the pandas call sites, not profiled measurements.
