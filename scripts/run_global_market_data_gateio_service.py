#!/usr/bin/env python3
"""Systemd entry point for the existing Gate.io public candle collector."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forward.global_market_data_gateio_v1 import run

if __name__ == "__main__":
    run()
