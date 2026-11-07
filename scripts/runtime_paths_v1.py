"""Resolve immutable release code separately from shared mutable runtime data."""
from __future__ import annotations

import os
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path(os.environ.get("HES_DATA_ROOT", "/opt/hes-trade-agent")).expanduser().resolve()
