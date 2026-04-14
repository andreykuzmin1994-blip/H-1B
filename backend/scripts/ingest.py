#!/usr/bin/env python
"""Top-level ingestion CLI entrypoint."""
import sys
from pathlib import Path

# Allow running from the scripts/ directory without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h1b_engine.ingest.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
