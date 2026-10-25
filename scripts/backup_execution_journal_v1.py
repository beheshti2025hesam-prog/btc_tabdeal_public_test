"""Operator CLI for the existing execution journal's verified SQLite backup."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from forward.sqlite_backup_v1 import (
    SQLiteBackupError,
    create_verified_backup,
    restore_verified_backup,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--backup", nargs=2, metavar=("SOURCE_DB", "BACKUP_DB"))
    actions.add_argument("--restore", nargs=2, metavar=("BACKUP_DB", "DESTINATION_DB"))
    parser.add_argument("--overwrite", action="store_true",
                        help="allow restore to replace an existing destination database")
    args = parser.parse_args(argv)
    try:
        if args.backup:
            result = create_verified_backup(*args.backup)
        else:
            result = restore_verified_backup(
                args.restore[0], args.restore[1], overwrite=args.overwrite
            )
    except (OSError, SQLiteBackupError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
