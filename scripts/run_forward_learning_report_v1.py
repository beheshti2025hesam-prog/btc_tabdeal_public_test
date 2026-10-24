"""Generate a deterministic learning report from existing forward decision/outcome JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from forward.learning_evidence_adapter_v1 import build_report_from_artifacts, report_dict


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_jsonl:{path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"record_not_object:{path}:{line_number}")
            rows.append(row)
    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", required=True, type=Path, help="Immutable forward decision journal JSONL")
    parser.add_argument("--outcomes", required=True, type=Path, help="Separate reconciled outcome ledger JSONL")
    parser.add_argument("--output", type=Path, help="Optional report path; default prints JSON to stdout")
    parser.add_argument("--min-group-size", type=int, default=5)
    args = parser.parse_args(argv)
    try:
        report = build_report_from_artifacts(
            _read_jsonl(args.decisions),
            _read_jsonl(args.outcomes),
            min_group_size=args.min_group_size,
        )
        rendered = json.dumps(report_dict(report), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\\n"
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
