from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from scripts.ops.hes_smart_storage_manager_v1 import archive_inventory, build_report, compression_advice, load_inventory, restore_assessment

NOW=datetime(2026,11,15,15,0,tzinfo=timezone.utc)

def source_reports():
    idlm={"schema":"hes_data_lifecycle_audit_v1","mode":"READ_ONLY_DRY_RUN",
          "generated_at":NOW.isoformat(),"items":[]}
    cleanup={"schema":"hes_smart_cleanup_manager_v1","mode":"READ_ONLY_DEPENDENCY_AWARE_DRY_RUN",
      "generated_at":NOW.isoformat(),"source_audit_schema":idlm["schema"],
      "source_audit_generated_at":idlm["generated_at"],"source_audit_gate":{"status":"PASS","errors":[],"age_seconds":1},
      "dependency_scan":{"process_scan_errors":0,"scheduled_job_scan_errors":0,"unit_scan_errors":0,
                         "active_pointer_errors":[],"process_reference_count":2,"running_unit_reference_count":1,
                         "scheduled_job_reference_count":3},
      "inventory_items":2,"items":[
        {"path":"/var/tmp/a","classification":"REVIEW_TEMP","allocated_bytes":4096},
        {"path":"/var/backups/a","classification":"KEEP_BACKUP","allocated_bytes":8192}],
      "recovery_gate":{"full_restore_gate":"BLOCKED_NOT_PROVEN","cleanup_authorization":False}}
    return idlm,cleanup

def test_inventory_reuses_exact_idlm_and_cleanup_snapshot():
    idlm,cleanup=source_reports()
    result=load_inventory(idlm,cleanup,NOW)
    assert result["status"]=="PASS" and result["items"]==2
    assert result["classification_storage"]["KEEP_BACKUP"]["allocated_bytes"]==8192
    assert result["deletion_authorized"] is False

def test_stale_idlm_report_fails_closed():
    idlm,cleanup=source_reports()
    idlm["generated_at"]=(NOW-timedelta(minutes=16)).isoformat()
    with pytest.raises(ValueError,match="stale"): load_inventory(idlm,cleanup,NOW)

def test_cleanup_must_reference_exact_idlm_snapshot():
    idlm,cleanup=source_reports(); cleanup["source_audit_generated_at"]="2026-11-15T14:00:00+00:00"
    with pytest.raises(ValueError,match="exact IDLM"): load_inventory(idlm,cleanup,NOW)

def test_stale_cleanup_report_fails_closed():
    idlm,cleanup=source_reports()
    cleanup["generated_at"]=(NOW-timedelta(minutes=16)).isoformat()
    with pytest.raises(ValueError,match="Smart Cleanup report stale"): load_inventory(idlm,cleanup,NOW)

def test_missing_dependency_scan_field_fails_closed():
    idlm,cleanup=source_reports(); cleanup["dependency_scan"].pop("unit_scan_errors")
    with pytest.raises(ValueError,match="field missing"): load_inventory(idlm,cleanup,NOW)

def test_dependency_scan_error_blocks_inventory():
    idlm,cleanup=source_reports(); cleanup["dependency_scan"]["unit_scan_errors"]=1
    with pytest.raises(ValueError,match="dependency scan"): load_inventory(idlm,cleanup,NOW)

def test_missing_or_mismatched_schema_fails_closed():
    idlm,cleanup=source_reports(); cleanup["schema"]="wrong"
    with pytest.raises(ValueError,match="schema/mode"): load_inventory(idlm,cleanup,NOW)

def test_malformed_inventory_rows_fail_closed():
    idlm,cleanup=source_reports(); cleanup["items"][0].pop("path")
    with pytest.raises(ValueError,match="malformed"): load_inventory(idlm,cleanup,NOW)

def test_archive_inventory_detects_same_day_duplicates(tmp_path):
    (tmp_path/"hes-full-20261115T010000Z.tar.gz.gpg").write_bytes(b"a"*10)
    (tmp_path/"hes-full-20261115T020000Z.tar.gz.gpg").write_bytes(b"b"*20)
    (tmp_path/"hes-full-20261115T020000Z.tar.gz.gpg.sha256").write_text("sidecar")
    result=archive_inventory(tmp_path,"hes-full-")
    assert result["archive_count"]==2 and result["total_bytes"]==30
    assert len(result["same_day_multiple"]["20261115"])==2

def test_missing_archive_directory_is_not_reported_as_empty_success(tmp_path):
    result=archive_inventory(tmp_path/"missing","hes-full-")
    assert result["status"]=="MISSING" and result["errors"]==1

def test_compression_evidence_is_required_and_validated():
    assert compression_advice(None)["status"]=="NO_BENCHMARK"
    assert compression_advice({"source_bytes":100})["status"]=="INVALID_EVIDENCE"

def test_zstd_recommendation_is_prototype_only():
    result=compression_advice({"source_bytes":1000,"gzip1_bytes":600,"zstd3_bytes":580,"zstd9_bytes":500})
    assert result["recommendation"]=="PROTOTYPE_ZSTD9_FOR_LOCAL_BACKUP_V2"
    assert result["legacy_gzip_restore_required"] and not result["production_format_changed"]

def test_small_gain_keeps_gzip():
    result=compression_advice({"source_bytes":1000,"gzip1_bytes":600,"zstd3_bytes":598,"zstd9_bytes":590})
    assert result["recommendation"]=="KEEP_GZIP1"

def test_report_has_no_mutation_authority():
    idlm,cleanup=source_reports()
    result=build_report(idlm=idlm,cleanup=cleanup,now=NOW,disk={"pressure":"WARN"},
                        quota={"status":"READ_OK","free_bytes":123},evidence=None)
    assert result["inventory_source"]=="IDLM_V1_PLUS_SMART_CLEANUP_MANAGER_V1"
    assert result["policy"]["deletion_authorized"] is False
    assert result["policy"]["move_authorized"] is False
    assert result["policy"]["compression_authorized"] is False
    assert result["policy"]["automatic_cleanup_timer_authorized"] is False
    assert result["inventory"]["recovery_gate"]["full_restore_gate"]=="BLOCKED_NOT_PROVEN"
    assert result["recovery_assessment"]["status"] == "NOT_PROVEN"
    assert result["policy"]["full_archive_restore_verified"] is False
    assert "remote restore" in result["policy"]["backup_retention"]

def test_nested_full_scope_compression_evidence_is_parsed_without_overclaiming_local_scope():
    evidence={
      "schema":"hes_zstd_full_scope_benchmark_v1",
      "source":"exact offsite builder include-list semantics; active and rollback releases included",
      "source_bytes":4077824000,
      "results":{
        "gzip_1":{"bytes":1601064546},
        "zstd_3_single_thread":{"bytes":1407220695},
        "zstd_9_single_thread":{"bytes":1228742799}
      },
      "gpg_encryption_included_in_size_benchmark":False,
      "restore_roundtrip_status":"PASS_FULL_SCOPE_ZSTD_GPG_STREAM_TEST"
    }
    result=compression_advice(evidence)
    assert result["status"]=="FULL_SCOPE_STREAM_BENCHMARK_NOT_LOCAL_BACKUP_PROOF"
    assert result["zstd9_vs_gzip1_saving_percent"]==23.25
    assert result["recommendation"]=="PROTOTYPE_ZSTD9_FOR_LOCAL_BACKUP_V2"
    assert result["legacy_gzip_restore_required"] is True
    assert result["production_format_changed"] is False
    assert result["roundtrip_status"] == "PASS_FULL_SCOPE_ZSTD_GPG_STREAM_TEST"
    assert result["compression_authorized"] is False

def test_storage_budget_counts_direct_children_once_and_separates_backup_copies():
    from scripts.ops.hes_smart_storage_manager_v1 import storage_budget
    items=[
      {"path":"/opt/hes-trade-agent/releases","allocated_bytes":500},
      {"path":"/opt/hes-trade-agent/releases/active","allocated_bytes":100},
      {"path":"/opt/hes-trade-agent/data","allocated_bytes":200},
      {"path":"/srv/hes-evidence/gateio","allocated_bytes":50},
      {"path":"/srv/hes-evidence/gateio/raw","allocated_bytes":25},
      {"path":"/var/backups/hes-trade-agent/encrypted-local","allocated_bytes":1000},
      {"path":"/var/backups/hes-trade-agent/encrypted-local/a.gpg","allocated_bytes":500},
    ]
    result=storage_budget(items,target_gib=0)
    assert result["components_bytes"]=={
      "project_checkout_including_releases_candidates_worktrees":700,
      "independent_evidence_store":50,
      "local_backups_and_offsite_staging":1000
    }
    assert result["total_local_hes_bytes_including_backups"]==1750
    assert result["complete_footprint_within_target"] is False
    assert result["agent_core_bytes_excluding_backup_copies"]==750
    assert result["no_data_mutated"] is True

def test_local_backup_benchmark_is_distinguished_from_offsite_scope():
    evidence={
      "schema":"hes_local_backup_zstd_benchmark_v1",
      "scope":"local_backup",
      "source_bytes":7315415040,
      "results":{
        "gzip_1":{"bytes":2453424957},
        "zstd_3_single_thread":{"bytes":2193274296},
        "zstd_9_single_thread":{"bytes":1920590051}
      },
      "gpg_encryption_included_in_size_benchmark":False,
      "archive_written":False,
      "fixture_roundtrip_status":"PASS_ZSTD_GPG_AND_LEGACY_GZIP_VERIFIER_FIXTURES"
    }
    result=compression_advice(evidence)
    assert result["status"]=="LOCAL_BACKUP_STREAM_BENCHMARK"
    assert result["zstd9_vs_gzip1_saving_percent"]==21.72
    assert result["recommendation"]=="PROTOTYPE_ZSTD9_FOR_LOCAL_BACKUP_V2"
    assert result["production_format_changed"] is False
    assert result["roundtrip_status"] == "PASS_ZSTD_GPG_AND_LEGACY_GZIP_VERIFIER_FIXTURES"
    assert result["compression_authorized"] is False


def valid_full_restore_evidence():
    return {
        "schema": "hes_restic_fullscope_restore_drill_v1",
        "integrity_check": "PASS_READ_DATA_45_OF_45_PACKS_NO_ERRORS",
        "full_restore": {
            "status": "PASS",
            "restic_verify": "PASS_32927_FILES",
            "restored_files": 32927,
            "restored_file_bytes": 4475458842,
            "required_recovery_paths": "PASS_18_OF_18",
            "static_content_comparison": "PASS_8_FILES",
        },
    }


def test_full_archive_restore_evidence_is_distinguished_from_replacement_host_restore():
    idlm, cleanup = source_reports()
    result = build_report(
        idlm=idlm,
        cleanup=cleanup,
        now=NOW,
        disk={"pressure": "WARN"},
        quota={"status": "READ_OK", "free_bytes": 123},
        restore_evidence=valid_full_restore_evidence(),
    )
    assert result["recovery_assessment"]["status"] == "FULL_ARCHIVE_RESTORE_VERIFIED"
    assert result["recovery_assessment"]["full_archive_restore"] == "PASS"
    assert result["recovery_assessment"]["replacement_host_restore"] == "NOT_PROVEN"
    assert result["recovery_assessment"]["remote_restore"] == "NOT_RUN"
    assert result["recovery_assessment"]["cleanup_authorized"] is False
    assert result["policy"]["full_archive_restore_verified"] is True
    assert result["policy"]["replacement_host_restore_proven"] is False
    assert result["policy"]["deletion_authorized"] is False
    assert result["inventory"]["recovery_gate"]["full_restore_gate"] == "BLOCKED_NOT_PROVEN"


def test_missing_restore_evidence_keeps_archive_restore_not_proven():
    result = restore_assessment(None)
    assert result["status"] == "NOT_PROVEN"
    assert result["full_archive_restore"] == "NOT_PROVEN"
    assert result["cleanup_authorized"] is False


def test_invalid_or_incomplete_restore_evidence_fails_closed():
    evidence = valid_full_restore_evidence()
    evidence["full_restore"]["restored_files"] = 0
    result = restore_assessment(evidence)
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert result["full_archive_restore"] == "NOT_PROVEN"
    assert result["cleanup_authorized"] is False
