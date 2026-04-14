#!/usr/bin/env python
"""Top-level scoring CLI entrypoint."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from h1b_engine.score.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
