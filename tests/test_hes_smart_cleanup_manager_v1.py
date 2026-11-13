from datetime import datetime, timezone

from scripts.ops.hes_smart_cleanup_manager_v1 import build_manager_report


def _audit(items=None):
    return {
        "schema": "hes_data_lifecycle_audit_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY_DRY_RUN",
        "disk": {"total_bytes": 1000, "used_bytes": 800, "free_bytes": 200, "free_percent": 20},
        "worktree_registry": {"paths": ["/opt/hes-trade-agent/.worktrees/example"]},
        "items": items or [],
    }


def _build_report(audit, **kwargs):
    kwargs.setdefault("scheduled_refs", [])
    kwargs.setdefault("scheduled_errors", 0)
    return build_manager_report(audit, **kwargs)


def test_unknown_and_protected_items_are_keep_and_never_deleted():
    report = _build_report(
        _audit([
            {"path": "/srv/hes-evidence", "classification": "KEEP_EVIDENCE", "allocated_bytes": 10},
            {"path": "/opt/unknown", "classification": "KEEP_UNKNOWN", "allocated_bytes": 20},
        ]),
        proc_refs=[], proc_errors=0,
        unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert [x["decision"] for x in report["items"]] == ["KEEP", "KEEP"]
    assert report["summary"]["delete_authorized"] == 0
    assert report["recovery_gate"]["cleanup_authorization"] is False


def test_open_process_reference_blocks_review_candidate():
    report = _build_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE", "allocated_bytes": 10}]),
        proc_refs=[{"pid": 42, "comm": "worker", "kind": "fd", "path": "/tmp/cache-x/blob"}],
        proc_errors=0, unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    row = report["items"][0]
    assert row["dependency_status"] == "BLOCKED_REFERENCED"
    assert row["decision"] == "KEEP"


def test_registered_worktree_and_active_release_are_protected():
    report = _build_report(
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
    report = _build_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=1, unit_refs=[], unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "UNKNOWN_FAIL_CLOSED"
    assert report["items"][0]["decision"] == "KEEP"


def test_no_live_reference_still_means_review_only_not_delete():
    report = _build_report(
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
    report = _build_report(audit, proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={})
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
    report = _build_report(_audit([]), proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status=backup)
    assert report["recovery_gate"]["backup_integrity_gate"] == "INCOMPLETE"
    backup["remote_hash_check"] = "PASS"
    report = _build_report(_audit([]), proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status=backup)
    assert report["recovery_gate"]["backup_integrity_gate"] == "PASS"



def test_active_release_target_blocks_candidate_even_if_classified_review():
    report = _build_report(
        _audit([{"path": "/opt/hes-trade-agent/releases/f5-active", "classification": "REVIEW_STALE_TEMP"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0, backup_status={},
        active_targets=["/opt/hes-trade-agent/releases/f5-active"], pointer_errors=[],
    )
    assert report["items"][0]["active_or_rollback_release_related"] is True
    assert report["items"][0]["decision"] == "KEEP"


def test_unresolved_release_pointer_fails_closed():
    report = _build_report(
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
    report = _build_report(
        _audit([{"path": "/var/cache/hes-cache", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0,
        unit_refs=[{"unit": "hes-worker.service", "property": "CacheDirectory_resolved", "value": "/var/cache/hes-cache"}],
        unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "BLOCKED_REFERENCED"
    assert report["items"][0]["decision"] == "KEEP"


def test_unverified_worktree_registry_fails_closed():
    audit = _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}])
    audit["worktree_registry"]["error"] = "git_worktree_list_failed"
    report = _build_report(audit, proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status={}, active_targets=[], pointer_errors=[])
    assert report["source_audit_gate"]["status"] == "FAIL_CLOSED"
    assert report["items"][0]["dependency_status"] == "UNKNOWN_FAIL_CLOSED"
    assert report["items"][0]["decision"] == "KEEP"


def test_stale_source_audit_fails_closed():
    audit = _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}])
    audit["generated_at"] = "2026-11-11T00:00:00+00:00"
    report = _build_report(audit, now=datetime(2026, 11, 12, tzinfo=timezone.utc),
                                  proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status={}, active_targets=[], pointer_errors=[])
    assert "source_audit_stale_or_future_dated" in report["source_audit_gate"]["errors"]
    assert report["items"][0]["decision"] == "KEEP"


def test_wrong_source_schema_fails_closed():
    audit = _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}])
    audit["schema"] = "unexpected"
    report = _build_report(audit, proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                                  backup_status={}, active_targets=[], pointer_errors=[])
    assert "unexpected_source_audit_schema" in report["source_audit_gate"]["errors"]
    assert report["items"][0]["decision"] == "KEEP"


def test_systemd_environment_file_reference_blocks_candidate():
    report = _build_report(
        _audit([{"path": "/etc/default/hes-worker", "classification": "REVIEW_STALE_TEMP"}]),
        proc_refs=[], proc_errors=0,
        unit_refs=[{"unit": "hes-worker.service", "property": "EnvironmentFiles", "value": "-/etc/default/hes-worker"}],
        unit_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "BLOCKED_REFERENCED"
    assert report["items"][0]["decision"] == "KEEP"


def test_cron_reference_blocks_review_candidate():
    report = _build_report(
        _audit([{"path": "/opt/hes-trade-agent/data/important.csv", "classification": "REVIEW_STALE_TEMP"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
        scheduled_refs=[{"unit": "/etc/cron.d/job", "property": "cron", "value": "python /opt/hes-trade-agent/data/important.csv"}],
        scheduled_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "BLOCKED_REFERENCED"
    assert report["items"][0]["decision"] == "KEEP"


def test_enabled_user_systemd_reference_blocks_review_candidate():
    report = _build_report(
        _audit([{"path": "/home/alice/.cache/hes", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
        scheduled_refs=[{"unit": "/etc/systemd/user/foo.service", "property": "enabled_user_systemd_unit",
                         "value": "WorkingDirectory=/home/alice/.cache/hes"}],
        scheduled_errors=0, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "BLOCKED_REFERENCED"
    assert report["items"][0]["decision"] == "KEEP"


def test_scheduled_job_scan_error_fails_closed():
    report = _build_report(
        _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
        scheduled_refs=[], scheduled_errors=1, backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["dependency_status"] == "UNKNOWN_FAIL_CLOSED"
    assert report["items"][0]["decision"] == "KEEP"


def test_unknown_classification_fails_closed_to_keep():
    report = _build_report(
        _audit([{"path": "/tmp/cache-x", "classification": "DELETE_ME"}]),
        proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
        backup_status={}, active_targets=[], pointer_errors=[],
    )
    assert report["items"][0]["decision"] == "KEEP"
    assert report["items"][0]["automatic_action"] == "NONE"


def test_relative_worktree_registry_path_fails_closed():
    audit = _audit([{"path": "/tmp/cache-x", "classification": "REVIEW_REGENERABLE_CACHE"}])
    audit["worktree_registry"]["paths"] = ["relative/worktree"]
    report = _build_report(audit, proc_refs=[], proc_errors=0, unit_refs=[], unit_errors=0,
                           backup_status={}, active_targets=[], pointer_errors=[])
    assert "worktree_registry_paths_invalid" in report["source_audit_gate"]["errors"]
    assert report["items"][0]["decision"] == "KEEP"



def test_cron_symlink_target_is_inventoried(tmp_path):
    from scripts.ops.hes_smart_cleanup_manager_v1 import _register_scheduled_file

    target = tmp_path / "job-target.sh"
    target.write_text("#!/bin/sh\necho /opt/hes-trade-agent/data/important.csv\n")
    cron_dir = tmp_path / "cron.daily"
    cron_dir.mkdir()
    link = cron_dir / "job"
    link.symlink_to(target)
    files = {}
    refs = []
    errors = _register_scheduled_file(link, "cron", None, None, files, refs)

    assert errors == 0
    assert target in files
    assert any(row["property"] == "cron_symlink_path" and row["value"] == str(link) for row in refs)
    assert any(row["property"] == "cron_symlink_target" and row["value"] == str(target) for row in refs)


def test_dangling_cron_symlink_fails_closed(tmp_path):
    from scripts.ops.hes_smart_cleanup_manager_v1 import _register_scheduled_file

    link = tmp_path / "dangling-job"
    link.symlink_to(tmp_path / "missing-target")
    files = {}
    refs = []
    errors = _register_scheduled_file(link, "cron", None, None, files, refs)

    assert errors == 1
    assert any(row["property"] == "cron_unresolved_path" for row in refs)


def test_systemd_path_match_parses_quoted_paths_with_spaces():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    path = "/var/cache/hes agent/cache.bin"
    refs = [{"unit": "hes-agent.service", "property": "ExecStart", "value": f'/usr/bin/python3 "{path}"'}]
    matches = _matches_unit(path, refs)
    assert len(matches) == 1
    assert matches[0]["match_reason"] == "NORMALIZED_PATH_TOKEN_MATCH"


def test_systemd_path_match_decodes_hex_escaped_spaces():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    path = "/var/cache/hes agent/cache.bin"
    refs = [{"unit": "hes-agent.service", "property": "ExecStart", "value": r"/usr/bin/python3 /var/cache/hes\x20agent/cache.bin"}]
    matches = _matches_unit(path, refs)
    assert len(matches) == 1
    assert matches[0]["match_reason"] == "NORMALIZED_PATH_TOKEN_MATCH"


def test_unresolved_environment_path_fails_closed_for_candidate():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    refs = [{"unit": "hes-agent.service", "property": "ExecStart", "value": "/usr/bin/python3 ${HES_CACHE_ROOT}/job.py"}]
    matches = _matches_unit("/var/cache/hes-agent", refs)
    assert len(matches) == 1
    assert matches[0]["match_reason"] == "UNPARSED_PATH_DECLARATION_FAIL_CLOSED"


def test_active_user_manager_without_bus_fails_closed(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from scripts.ops import hes_smart_cleanup_manager_v1 as manager

    def fake_run(command, **kwargs):
        if command[:2] == ["loginctl", "list-users"]:
            return SimpleNamespace(returncode=0, stdout="1000 alice -\n")
        if command[:2] == ["loginctl", "show-user"]:
            return SimpleNamespace(returncode=0, stdout="State=active\nLinger=no\nRuntimePath=/run/user/1000\n")
        raise AssertionError(command)

    monkeypatch.setattr(manager.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "exists", lambda self: False)
    refs, errors = manager._user_systemd_runtime_references()
    assert refs == []
    assert errors == 1


def test_active_user_manager_units_are_queried(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    from scripts.ops import hes_smart_cleanup_manager_v1 as manager

    def fake_run(command, **kwargs):
        if command[:2] == ["loginctl", "list-users"]:
            return SimpleNamespace(returncode=0, stdout="1000 alice -\n")
        if command[:2] == ["loginctl", "show-user"]:
            return SimpleNamespace(returncode=0, stdout="State=active\nLinger=no\nRuntimePath=/run/user/1000\n")
        if command[0] == "runuser" and "list-units" in command:
            return SimpleNamespace(returncode=0, stdout="hes-user.service loaded active running User HES service\n")
        if command[0] == "runuser" and "list-unit-files" in command:
            return SimpleNamespace(returncode=0, stdout="hes-user.service enabled enabled\n")
        if command[0] == "runuser" and "show" in command:
            return SimpleNamespace(returncode=0, stdout="WorkingDirectory=/var/cache/hes-user\nExecStart={ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 /var/cache/hes-user/job.py ; }\n")
        raise AssertionError(command)

    original_exists = Path.exists
    monkeypatch.setattr(manager.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "exists", lambda self: True if str(self) == "/run/user/1000/bus" else original_exists(self))
    refs, errors = manager._user_systemd_runtime_references()
    assert errors == 0
    assert any(row["unit"] == "alice:hes-user.service" and row["property"] == "WorkingDirectory" for row in refs)



def test_generic_root_context_does_not_reference_every_candidate():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    refs = [
        {"unit": "generic.service", "property": "WorkingDirectory", "value": "/"},
        {"unit": "/etc/crontab", "property": "cron", "value": "cd /"},
        {"unit": "tmpfiles.conf", "property": "system_maintenance_config", "value": "q /var 0755 - - -"},
    ]
    assert _matches_unit("/var/backups/hes-trade-agent/offsite-staging", refs) == []


def test_explicit_cache_directory_access_blocks_nested_candidate():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    refs = [{"unit": "hes-agent.service", "property": "CacheDirectory_resolved", "value": "/var/cache/hes-agent"}]
    matches = _matches_unit("/var/cache/hes-agent/state/cache.db", refs)
    assert len(matches) == 1


def test_mount_requirement_does_not_claim_every_child_file():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    refs = [{"unit": "tmp.service", "property": "RequiresMountsFor", "value": "/var/tmp"}]
    assert _matches_unit("/var/tmp/old-candidate", refs) == []


def test_systemd_runtime_glob_is_scoped_to_stable_prefix():
    from scripts.ops.hes_smart_cleanup_manager_v1 import _matches_unit

    refs = [{"unit": "systemd-tmpfiles", "property": "system_maintenance_config", "value": "x /tmp/systemd-private-%b-*"}]
    assert len(_matches_unit("/tmp/systemd-private-abc123", refs)) == 1
    assert _matches_unit("/tmp/hes-unrelated", refs) == []
