#!/usr/bin/env python3
"""CLI entry point for the paired Standard-versus-Fast latency comparison."""

from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from product_fast_latency_comparison import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
