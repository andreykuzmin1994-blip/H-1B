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

## Status

Full Sprint 1-5 scaffolding implemented. See spec for phased build details.
