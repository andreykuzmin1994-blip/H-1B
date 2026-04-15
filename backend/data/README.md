## Data directory

Where raw source files live before ingestion, plus small fixtures for a
smoke test of the pipeline.

```
data/
  raw/
    lca/         DOL OFLC LCA disclosure files (.xlsx or .csv; year in filename)
    uscis_hub/   USCIS H-1B Employer Data Hub (.csv or .xlsx; year in filename)
    whd/         DOL Wage & Hour Division enforcement (.csv)
    bls/         BLS OEWS wage benchmark files (.xlsx; year in filename)
    warn/        WARN Act layoff notices (.csv; optional per-state subdirs)
  fixtures/
    smoke/       Tiny synthetic files used by `scripts/smoke_test.sh`
```

The `raw/` subdirectories are `.gitignore`d (see repo root `.gitignore`) —
only the `.gitkeep` markers and per-source README notes are tracked.

See `docs/operations.md` for the full ingestion workflow and
`scripts/smoke_test.sh` for an end-to-end validation you can run before
dropping real files.
