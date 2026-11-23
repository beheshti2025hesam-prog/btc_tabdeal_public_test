import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops import hes_restic_restore_drill_v1 as drill


def test_restore_space_preflight_uses_full_snapshot_size_and_safety_margin(tmp_path, monkeypatch):
    monkeypatch.setattr(drill.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"total_size": 10_000})))
    monkeypatch.setattr(drill.shutil, "disk_usage", lambda p: SimpleNamespace(total=50_000, used=20_000, free=20_000))
    result = drill.restore_space_preflight("snapshot-a", tmp_path, safety_margin_bytes=2_000, safety_margin_percent=10)
    assert result["status"] == "PASS"
    assert result["restore_size_bytes"] == 10_000
    assert result["safety_margin_bytes"] == 2_000
    assert result["required_free_bytes"] == 12_000
    assert result["available_free_bytes"] == 20_000
    assert result["estimate_scope"] == "FULL_SNAPSHOT_CONSERVATIVE_UPPER_BOUND"


def test_restore_space_preflight_defers_before_restore_when_space_is_short(tmp_path, monkeypatch):
    monkeypatch.setattr(drill.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=json.dumps({"total_size": 10_000})))
    monkeypatch.setattr(drill.shutil, "disk_usage", lambda p: SimpleNamespace(total=50_000, used=20_000, free=11_999))
    result = drill.restore_space_preflight("snapshot-a", tmp_path, safety_margin_bytes=2_000, safety_margin_percent=10)
    assert result["status"] == "DEFERRED_INSUFFICIENT_SPACE"
    assert result["required_free_bytes"] == 12_000


def test_run_drill_does_not_create_temp_restore_when_preflight_defers(tmp_path, monkeypatch):
    monkeypatch.setattr(drill, "restore_space_preflight", lambda *a, **k: {
        "status": "DEFERRED_INSUFFICIENT_SPACE", "required_free_bytes": 12_000, "available_free_bytes": 11_999
    })
    monkeypatch.setattr(drill.tempfile, "mkdtemp", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not create temp dir")))
    args = SimpleNamespace(snapshot_id="snapshot-a", temp_parent=str(tmp_path), safety_margin_bytes=2000,
                           safety_margin_percent=10, evidence_sample="/missing", active_release="/opt/active",
                           rollback_release="/opt/rollback", dashboard_release="/opt/dashboard",
                           strategy_ref="refs/heads/example", strategy_commit="a"*40, marker=str(tmp_path/"marker"))
    with pytest.raises(drill.InsufficientRestoreSpace):
        drill.run_drill(args)
    assert not (tmp_path / "marker").exists()