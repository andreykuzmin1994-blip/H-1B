# H-1B Transparency & Accountability Engine

A public-interest tool that connects DOL OFLC LCA disclosure data, USCIS H-1B
employer data, DOL WHD enforcement data, and BLS OEWS wage benchmarks into a
single system that surfaces anomalies, maps entity relationships, and generates
formatted enforcement tips.

See [`h1b_transparency_engine_spec.md`](./h1b_transparency_engine_spec.md) for
the full project specification.

## Repository layout

```
backend/                  Python data pipeline + scoring + investigation engine
  h1b_engine/             Library code
    db/                   SQLAlchemy models + session management
    ingest/               Source-specific ingestion scripts
    score/                Anomaly scoring
    graph/                Entity relationship graph
    investigate/          AutoResearch investigation framework
    credentials/          Personnel Look-Up / credential verification tool
    utils/                Shared helpers (wage normalization, name normalization)
  migrations/             Alembic migrations
  scripts/                CLI entrypoints (ingest.py, score.py, graph.py, investigate.py, personnel.py)
  tests/                  Unit tests
frontend/                 Next.js 14 (App Router) web dashboard
  app/                    Routes
  components/             React components
  lib/                    DB client + helpers
  prisma/                 Schema + generated client
docker/                   Docker compose for PostgreSQL
docs/                     Operating documentation
reports/                  Generated investigation reports (gitignored)
```

## Quick start

```bash
# Bring up Postgres
docker compose -f docker/docker-compose.yml up -d

# Backend
cd backend
pip install -e .
alembic upgrade head

# Sprint 1: ingest data
python scripts/ingest.py lca --fiscal-year 2024
python scripts/ingest.py uscis-hub --fiscal-year 2024
python scripts/ingest.py whd-enforcement
python scripts/ingest.py violators
python scripts/ingest.py bls-oews --year 2024
# WARN Act mass-layoff notices (state CSVs under data/raw/warn/<XX>/, or a single file)
python scripts/ingest.py warn

# Sprint 2: score
python scripts/score.py run

# Sprint 3: graph
python scripts/graph.py build-all

# Sprint 5: investigate
python scripts/investigate.py --employer-id 1 --output report

# Sprint 6: personnel credential verification (after ingesting I-129 / FOIA / tip data)
python scripts/personnel.py bootstrap            # seed diploma-mill + evaluator lists
python scripts/personnel.py lookup --employer-id 1
python scripts/personnel.py lookup --beneficiary-id 42 --json-out reports/b42.json

# Frontend
cd ../frontend
npm install
npx prisma generate
npm run dev
```

## Public API stance

The `/api/v1/*` endpoints are intentionally unauthenticated. This is a
public-interest transparency tool built on public-record data. Do not add auth
gates without discussion.

Abuse control is per-IP rate limiting (`frontend/lib/ratelimit.ts`). Defaults:
60 requests/minute, sliding window. Tune via `RATELIMIT_MAX` /
`RATELIMIT_WINDOW`. For multi-instance deployments set `UPSTASH_REDIS_REST_URL`
and `UPSTASH_REDIS_REST_TOKEN` — the in-memory fallback doesn't survive restarts
or shard across replicas.

Other hardening: strict CSP + security headers in `next.config.js`,
Server Actions `allowedOrigins` driven by the `ALLOWED_ORIGINS` env var (wildcard
is not permitted), Postgres bound to `127.0.0.1` in the dev compose file with
credentials that must be set in `docker/.env`.

## Status

Full Sprint 1-5 scaffolding implemented. See spec for phased build details.
