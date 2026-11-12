from datetime import datetime, timezone

from scripts.ops.hes_smart_cleanup_manager_v1 import build_manager_report


def _audit(items=None):
    return {
        "schema": "hes_data_lifecycle_audit_v1",
        "generated_at": "2026-11-12T00:00:00+00:00",
        "disk": {"total_bytes": 1000, "used_bytes": 800, "free_bytes": 200, "free_percent": 20},
        "worktree_registry": {"paths": ["/opt/hes-trade-agent/.worktrees/example"]},
        "items": items or [],
    }


def test_unknown_and_protected_items_are_keep_and_never_deleted():
    report = build_manager_report(
        _audit([
            {"path": "/srv/hes-evidence", "classification": "KEEP_EVIDENCE", "allocated_bytes": 10},
            {"path": "/opt/unknown", "classification": "KEEP_UNKNOWN", "allocated_bytes": 20},
        ]),
        now=datetime(2026, 11, 12, tzinfo=timezone.utc), proc_refs=[], proc_errors=0,
        unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert [x["decision"] for x in report["items"]] == ["KEEP", "KEEP"]
    assert report["summary"]["delete_authorized"] == 0
    assert report["recovery_gate"]["cleanup_authorization"] is False


def test_open_process_reference_blocks_review_candidate():
    report = build_manager_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE", "allocated_bytes": 10}]),
        proc_refs=[{"pid": 42, "comm": "worker", "kind": "fd", "path": "/tmp/cache-x/blob"}],
        proc_errors=0, unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    row = report["items"][0]
    assert row["dependency_status"] == "BLOCKED_REFERENCED"
    assert row["decision"] == "KEEP"


def test_registered_worktree_and_active_release_are_protected():
    report = build_manager_report(
        _audit([
            {"path": "/opt/hes-trade-agent/.worktrees/example", "classification": "REVIEW_STALE_TEMP"},
            {"path": "/opt/hes-trade-agent/releases", "classification": "KEEP_PROTECTED"},
        ]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["registered_worktree_related"] is True
    assert report["items"][0]["decision"] == "KEEP"
    assert report["items"][1]["decision"] == "KEEP"


def test_dependency_scan_error_fails_closed():
    report = build_manager_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=1, unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "UNKNOWN_FAIL_CLOSED"
    assert report["items"][0]["decision"] == "KEEP"


def test_no_live_reference_still_means_review_only_not_delete():
    report = build_manager_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, active_targets=[], pointer_errors=[],
        backup_status={"local_latest_sidecar_verified": True, "offsite_latest_sidecar_verified": True,
                       "dropbox_remote_latest": {"size_bytes": 10}, "dropbox_quota": {"free_bytes": 10}},
    )
    assert report["items"][0]["dependency_status"] == "NO_LIVE_REFERENCE_OBSERVED"
    assert report["items"][0]["decision"] == "REVIEW_ONLY"
    assert report["summary"]["delete_authorized"] == 0
    assert report["recovery_gate"]["full_restore_gate"] == "BLOCKED_NOT_PROVEN"


def test_disk_pressure_thresholds():
    audit = _audit([])
    audit["disk"]["free_percent"] = 8
    report = build_manager_report(audit, proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={})
    assert report["disk_capacity"]["pressure"] == "CRITICAL"


def test_backup_integrity_gate_requires_remote_hash_and_size_match():
    backup = {
        "local_latest_sidecar_verified": True,
        "offsite_latest_sidecar_verified": True,
        "remote_hash_check": "NOT_RUN",
        "offsite_latest": {"size_bytes": 100},
        "dropbox_remote_latest": {"size_bytes": 100},
        "dropbox_quota": {"free_bytes": 500},
    }
    report = build_manager_report(_audit([]), proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status=backup)
    assert report["recovery_gate"]["backup_integrity_gate"] == "INCOMPLETE"
    backup["remote_hash_check"] = "PASS"
    report = build_manager_report(_audit([]), proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status=backup)
    assert report["recovery_gate"]["backup_integrity_gate"] == "PASS"



def test_active_release_target_blocks_candidate_even_if_classified_review():
    report = build_manager_report(
        _audit([{"path": "/opt/hes-trade-agent/releases/f5-active", "classification": "REVIEW_STALE_TEMP"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={},
        active_targets=["/opt/hes-trade-agent/releases/f5-active"], pointer_errors=[],
    )
    assert report["items"][0]["active_or_rollback_release_related"] is True
    assert report["items"][0]["decision"] == "KEEP"


def test_unresolved_release_pointer_fails_closed():
    report = build_manager_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={},
        active_targets=[], pointer_errors=["pointer_unresolved"],
    )
    assert report["items"][0]["dependency_status"] == "UNKNOWN_FAIL_CLOSED"
    assert report["items"][0]["decision"] == "KEEP"


def test_systemd_cache_and_state_directories_expand_to_paths():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _expand_systemd_path_reference

    cache = _expand_systemd_path_reference("example.service", "CacheDirectory", "hes-cache another-cache")
    state = _expand_systemd_path_reference("example.service", "StateDirectory", "hes-state:hes-user")
    assert {row["value"] for row in cache if row["property"].endswith("_resolved")} == {
        "/var/cache/hes-cache", "/var/cache/another-cache"
    }
    assert any(row["value"] == "/var/lib/hes-state" for row in state)



def test_uninstantiated_systemd_templates_are_not_queried():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _is_concrete_systemd_unit

    assert _is_concrete_systemd_unit("hes-worker@instance.service") is True
    assert _is_concrete_systemd_unit("getty@.service") is False
    assert _is_concrete_systemd_unit("hes-cleanup@.timer") is False


def test_systemd_directory_reference_blocks_review_candidate():
    report = build_manager_report(
        _audit([{"path": "/var/cache/hes-cache", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0,
        unit_refs=[{"unit": "hes-worker.service", "property": "CacheDirectory_resolved", "value": "/var/cache/hes-cache"}],
        unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "BLOCKED_REFERENCED"
    assert report["items"][0]["decision"] == "KEEP"