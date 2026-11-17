#!/usr/bin/env python3
"""Reject mutable third-party GitHub Actions references in workflow files."""
from __future__ import annotations

import re
import sys
from pathlib import Path

_USE_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def find_unpinned_actions(workflows_dir: str | Path) -> list[str]:
    directory = Path(workflows_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"workflow directory does not exist: {directory}")
    failures: list[str] = []
    files = sorted((*directory.glob("*.yml"), *directory.glob("*.yaml")))
    if not files:
        return [f"{directory}: no workflow files found"]
    for path in files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = _USE_RE.match(line)
            if not match:
                continue
            reference = match.group(1)
            if reference.startswith("./"):
                continue  # Repository-local composite actions are versioned with this commit.
            if "@" not in reference:
                failures.append(f"{path}:{line_number}: external action has no immutable ref: {reference}")
                continue
            revision = reference.rsplit("@", 1)[1]
            if not _SHA_RE.fullmatch(revision):
                failures.append(f"{path}:{line_number}: action ref must be a full 40-character commit SHA: {reference}")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = find_unpinned_actions(root / ".github" / "workflows")
    if failures:
        print("WORKFLOW_ACTION_PIN_POLICY=FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("WORKFLOW_ACTION_PIN_POLICY=PASS")
    print("All external GitHub Actions are pinned to immutable 40-character commit SHAs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
