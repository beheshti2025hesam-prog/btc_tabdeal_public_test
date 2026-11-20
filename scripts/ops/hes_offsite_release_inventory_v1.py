#!/usr/bin/env python3
"""Discover every live HES release tree required for offsite recovery."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _validated_release(value: str | Path, root: Path, label: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{label} release target is missing or broken: {candidate}") from exc
    releases = (root / "releases").resolve(strict=True)
    if resolved.parent != releases or not resolved.is_dir():
        raise ValueError(f"{label} does not resolve to a direct release directory: {resolved}")
    return resolved


def discover_release_inventory(
    project_root: str | Path,
    deploy_state_root: str | Path,
) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=True)
    state_root = Path(deploy_state_root).resolve(strict=True)

    required = ("current", "current-before-4329a3df")
    for name in required:
        pointer = root / name
        if not pointer.is_symlink():
            raise ValueError(f"required release pointer is missing: {pointer}")

    pointers = {root / "current"}
    pointers.update(root.glob("*-current"))
    pointers.update(root.glob("current-before-*"))
    pointers.update(root.glob("current-rollback-*"))

    targets: dict[Path, set[str]] = {}

    def add(label: str, value: str | Path) -> None:
        resolved = _validated_release(value, root, label)
        targets.setdefault(resolved, set()).add(label)

    for pointer in sorted(pointers):
        if not pointer.is_symlink():
            continue
        add(pointer.name, pointer)

    dashboard_pointer = root / "dashboard-current"
    if dashboard_pointer.is_symlink():
        deployments = sorted(state_root.glob("dashboard-deploy-*/postdeploy.json"))
        rollback_value = None
        for record_path in reversed(deployments):
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"cannot read dashboard deployment record: {record_path}") from exc
            if record.get("result") != "DEPLOYED_HEALTHY":
                continue
            checks = record.get("checks") or {}
            rollback_value = checks.get("rollback_target") or record.get("previous_release")
            if rollback_value:
                break
        if not rollback_value:
            raise ValueError("dashboard-current exists but no verified dashboard rollback target was found")
        add("dashboard-rollback", rollback_value)

    release_targets = []
    for path, labels in sorted(targets.items(), key=lambda item: str(item[0])):
        release_targets.append(
            {
                "path": str(path),
                "archive_path": path.relative_to(Path("/")).as_posix(),
                "pointers": sorted(labels),
            }
        )

    if not release_targets:
        raise ValueError("no release trees were discovered")
    return {
        "schema": "hes_offsite_release_inventory_v1",
        "project_root": str(root),
        "release_targets": release_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--deploy-state-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inventory = discover_release_inventory(args.project_root, args.deploy_state_root)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "HES_OFFSITE_RELEASE_INVENTORY_OK "
        f"release_trees={len(inventory['release_targets'])} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
