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
    utils/                Shared helpers (wage normalization, name normalization)
  migrations/             Alembic migrations
  scripts/                CLI entrypoints (ingest.py, score.py, graph.py, investigate.py)
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

# Sprint 1a: fetch raw data (NEVER commit these — they're gitignored)
#   The DOL OFLC LCA quarterly dumps are multi-GB; convert to Parquet to
#   shrink 5-10x. The ingest pipeline reads .parquet natively.
python scripts/download_data.py fetch --source lca --url <DOL_URL> --convert
python scripts/download_data.py to-parquet --all      # bulk-convert existing CSVs

# Sprint 1b: ingest data (auto-detects .parquet / .csv / .xlsx in data/raw/<source>/)
python scripts/ingest.py lca --fiscal-year 2024
python scripts/ingest.py uscis-hub --fiscal-year 2024
python scripts/ingest.py whd-enforcement
python scripts/ingest.py violators
python scripts/ingest.py bls-oews --year 2024
# WARN Act mass-layoff notices (state files under data/raw/warn/<XX>/, or a single file)
python scripts/ingest.py warn

# Sprint 2: score
python scripts/score.py run

# Sprint 3: graph
python scripts/graph.py build-all

# Sprint 5: investigate
python scripts/investigate.py --employer-id 1 --output report

# Frontend
cd ../frontend
npm install
npx prisma generate
npm run dev
```

## Status

Full Sprint 1-5 scaffolding implemented. See spec for phased build details.
