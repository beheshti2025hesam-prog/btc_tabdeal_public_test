"""Generate a deterministic report from the existing forward decision journal and outcome directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from forward.learning_evidence_adapter_v1 import build_forward_learning_report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True, type=Path, help="Existing append-only forward decision journal JSONL")
    parser.add_argument("--outcomes-dir", required=True, type=Path, help="Directory of separate immutable forward outcome JSON artifacts")
    parser.add_argument("--output", type=Path, help="Optional report path; default prints JSON to stdout")
    parser.add_argument("--min-group-size", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        result = build_forward_learning_report(
            args.journal, args.outcomes_dir, min_group_size=args.min_group_size
        )
        rendered = json.dumps({
            "report": result.report.__dict__,
            "evidence_manifest": result.evidence_manifest,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError) as exc:
        print(f"LEARNING_REPORT_BLOCKED:{type(exc).__name__}:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
