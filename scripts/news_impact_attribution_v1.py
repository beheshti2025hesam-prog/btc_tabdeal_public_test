#!/usr/bin/env python3
"""Generate a read-only news-event / Gate.io candle response report."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parents[1]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from scripts.runtime_paths_v1 import DATA_ROOT
from core.market_intelligence.news_impact_attribution_v1 import evaluate_news_impact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", default=os.environ.get("HES_NEWS_MONITOR_STATE_DIR", "/var/lib/hes-news-monitor"))
    parser.add_argument("--data-root", default=str(DATA_ROOT))
    parser.add_argument("--output", default=str(DATA_ROOT / "data/forward/news_impact_attribution_v1.json"))
    args = parser.parse_args()

    report = evaluate_news_impact(state_dir=args.state_dir, data_root=args.data_root)
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    print(json.dumps({
        "status": "OK",
        "output": str(destination),
        "event_clusters": report["event_cluster_count"],
        "matured": sum(event["status"] == "MATURED" for event in report["events"]),
        "pending": sum(event["status"] == "PENDING" for event in report["events"]),
        "output_sha256": report["output_sha256"],
        "source": report["source"],
        "source_reader": report["source_reader"],
        "news_alone_can_authorize_trade": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
