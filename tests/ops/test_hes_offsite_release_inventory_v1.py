import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = ROOT / "scripts" / "ops" / "hes_offsite_release_inventory_v1.py"
SPEC = importlib.util.spec_from_file_location("hes_offsite_release_inventory_v1", HELPER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _release(root: Path, name: str) -> Path:
    path = root / "releases" / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "release-marker.txt").write_text(name, encoding="utf-8")
    return path


def _pointer(root: Path, name: str, target: Path) -> None:
    (root / name).symlink_to(target, target_is_directory=True)


def _fixture(tmp_path: Path):
    root = tmp_path / "opt" / "hes-trade-agent"
    (root / "releases").mkdir(parents=True)
    state = tmp_path / "var" / "lib" / "hes-operational-health"
    state.mkdir(parents=True)
    current = _release(root, "core-current")
    core_rollback = _release(root, "core-rollback")
    dashboard = _release(root, "dashboard-current")
    dashboard_rollback = _release(root, "dashboard-rollback")
    precision = _release(root, "precision-current")
    paper_rollback = _release(root, "paper-rollback")
    _pointer(root, "current", current)
    _pointer(root, "current-before-4329a3df", core_rollback)
    _pointer(root, "dashboard-current", dashboard)
    _pointer(root, "precision-current", precision)
    _pointer(root, "current-rollback-20261119-test", paper_rollback)
    deployment = state / "dashboard-deploy-20261120T042722Z"
    deployment.mkdir()
    (deployment / "postdeploy.json").write_text(
        json.dumps(
            {
                "result": "DEPLOYED_HEALTHY",
                "checks": {"rollback_target": str(dashboard_rollback)},
            }
        ),
        encoding="utf-8",
    )
    return root, state, {
        current,
        core_rollback,
        dashboard,
        dashboard_rollback,
        precision,
        paper_rollback,
    }


def test_inventory_includes_all_live_and_verified_rollback_release_trees(tmp_path):
    root, state, expected = _fixture(tmp_path)
    result = MODULE.discover_release_inventory(root, state)
    actual = {Path(item["path"]) for item in result["release_targets"]}
    assert actual == expected
    assert result["schema"] == "hes_offsite_release_inventory_v1"
    assert all("/opt/hes-trade-agent/releases/" in "/" + item["archive_path"] for item in result["release_targets"])


def test_inventory_rejects_a_release_pointer_outside_the_release_root(tmp_path):
    root, state, _ = _fixture(tmp_path)
    external = tmp_path / "external-release"
    external.mkdir()
    (root / "dashboard-current").unlink()
    _pointer(root, "dashboard-current", external)
    try:
        MODULE.discover_release_inventory(root, state)
    except ValueError as exc:
        assert "direct release directory" in str(exc)
    else:
        raise AssertionError("external release pointer must fail closed")


def test_inventory_requires_a_verified_dashboard_rollback_target(tmp_path):
    root, state, _ = _fixture(tmp_path)
    for record in state.glob("dashboard-deploy-*/postdeploy.json"):
        record.unlink()
    try:
        MODULE.discover_release_inventory(root, state)
    except ValueError as exc:
        assert "no verified dashboard rollback target" in str(exc)
    else:
        raise AssertionError("dashboard backup without rollback evidence must fail closed")


def test_compact_builder_enforces_stream_cap_and_release_inventory():
    source = (ROOT / "scripts" / "ops" / "hes_dropbox_offsite_build_v2.sh").read_text()
    assert "hes_offsite_release_inventory_v1.py" in source
    assert '| head -c "$MAX_BYTES" > "$tmp"' in source
    assert "BUILD_REJECTED_STREAM_CAP" in source
    assert "--output -" in source
    assert "REMOTE_ACTION=NONE" in source
