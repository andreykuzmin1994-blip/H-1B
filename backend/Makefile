.PHONY: install migrate test smoke lint clean

install:
	pip install -e '.[dev]'

migrate:
	alembic upgrade head

test:
	python -m pytest tests/ -q

# End-to-end pipeline check against synthetic fixtures (SQLite, no Postgres).
# See scripts/smoke_test.py for the three-employer scenario it exercises.
smoke:
	python scripts/smoke_test.py

lint:
	ruff check h1b_engine tests
	mypy h1b_engine || true

clean:
	rm -rf data/_smoke_stage data/smoke.db
	find . -name __pycache__ -type d -exec rm -rf {} +
	find . -name '*.pyc' -delete
