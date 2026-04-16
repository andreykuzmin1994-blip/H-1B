# Operations guide

End-to-end operational runbook for the H-1B Transparency & Accountability
Engine.

## Prerequisites

- Docker + Docker Compose (for PostgreSQL)
- Python 3.10+
- Node 18+
- ~20 GB disk (full LCA history is ~6 GB raw, plus indices)

## 1. Bring up PostgreSQL

The compose file now hard-fails if `POSTGRES_USER` / `POSTGRES_PASSWORD` are
unset, and binds Postgres to `127.0.0.1` only (not reachable from the network).

```bash
cp docker/.env.example docker/.env   # edit POSTGRES_PASSWORD before first run
docker compose -f docker/docker-compose.yml --env-file docker/.env up -d
```

## 2. Install backend + run migrations

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # edit DATABASE_URL + API keys as needed
alembic upgrade head
```

## 3. Ingest data

Drop raw files into the expected directories (auto-created on first use):

| Source | Directory | Format |
|-------|-----------|--------|
| DOL LCA | `backend/data/raw/lca/` | Excel or CSV |
| USCIS Hub | `backend/data/raw/uscis_hub/` | CSV/Excel with year in filename |
| WHD | `backend/data/raw/whd/` | CSV |
| BLS OEWS | `backend/data/raw/bls/` | Excel with year in filename |

Then run:

```bash
python scripts/ingest.py lca --fiscal-year 2024
python scripts/ingest.py uscis-hub --fiscal-year 2024
python scripts/ingest.py whd-enforcement
python scripts/ingest.py violators
python scripts/ingest.py bls-oews --year 2024
```

Optional enrichment:

```bash
python scripts/ingest.py geocode --limit 5000
python scripts/ingest.py opencorporates --limit 5000   # requires API key
```

## 4. Score + graph

```bash
python scripts/score.py run
python scripts/graph.py build-all
python scripts/score.py run   # re-run so CONNECTED_TO_VIOLATOR uses new edges
```

## 5. Investigate flagged employers

```bash
# Single employer
python scripts/investigate.py run --employer-id 123 --output report

# Batch: every employer above a threshold
python scripts/investigate.py run --min-score 50 --output report --out-dir ../reports
```

## 6. Run the web dashboard

```bash
cd ../frontend
cp .env.example .env.local
npm install
npx prisma generate
npm run dev
```

Navigate to http://localhost:3000.

## Rate limiting

The public `/api/v1/*` endpoints are rate-limited per IP. Defaults: 60 requests
per minute, sliding window. Override via `RATELIMIT_MAX` / `RATELIMIT_WINDOW`
(Upstash duration literal, e.g. `30 s`, `1 m`, `1 h`).

For production / multi-replica deployments set `UPSTASH_REDIS_REST_URL` and
`UPSTASH_REDIS_REST_TOKEN`. The in-memory fallback is per-process (caps at 10k
tracked keys) and therefore under-counts behind a load balancer.

## Cron / incremental updates

Set up a periodic job to call `python scripts/ingest.py` with the incremental
DOL Data Portal API (no API key required):

```bash
0 4 * * * /app/scripts/incremental.sh
```

where `incremental.sh` hits the `apiprod.dol.gov/v4/` endpoint via
`h1b_engine.ingest.whd.fetch_incremental` and re-runs scoring.
