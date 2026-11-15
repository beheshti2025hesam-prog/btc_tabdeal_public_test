from pathlib import Path
from datetime import datetime, timezone
from scripts.ops.hes_smart_storage_manager_v1 import allocated_size, archive_inventory, build_report, compression_advice, disk_state

def test_missing_path_fails_closed(tmp_path):
    row=allocated_size(tmp_path/"missing")
    assert row["errors"]==1
    report=build_report(scopes={"missing":tmp_path/"missing"},disk={"pressure":"OK"})
    assert report["inventory"]["missing"]["policy"]=="UNKNOWN_KEEP"
    assert report["inventory"]["missing"]["action"]=="NONE"

def test_symlink_not_followed(tmp_path):
    target=tmp_path/"target"; target.mkdir(); (target/"payload").write_bytes(b"x"*4096)
    link=tmp_path/"link"; link.symlink_to(target,target_is_directory=True)
    row=allocated_size(link)
    assert row["symlinks"]==1 and row["files"]==0

def test_archive_inventory_and_same_day_duplicate_detection(tmp_path):
    (tmp_path/"hes-full-20261115T010000Z.tar.gz.gpg").write_bytes(b"a"*10)
    (tmp_path/"hes-full-20261115T020000Z.tar.gz.gpg").write_bytes(b"b"*20)
    (tmp_path/"hes-full-20261115T020000Z.tar.gz.gpg.sha256").write_text("sidecar")
    result=archive_inventory(tmp_path,"hes-full-")
    assert result["archive_count"]==2 and result["total_bytes"]==30
    assert len(result["same_day_multiple"]["20261115"])==2

def test_compression_requires_valid_evidence():
    assert compression_advice(None)["status"]=="NO_BENCHMARK"
    assert compression_advice({"source_bytes":100})["status"]=="INVALID_EVIDENCE"

def test_zstd_recommendation_is_prototype_only():
    result=compression_advice({"source_bytes":1000,"gzip1_bytes":600,"zstd3_bytes":580,"zstd9_bytes":500})
    assert result["recommendation"]=="PROTOTYPE_ZSTD9_NEW_ARCHIVES_ONLY"
    assert result["legacy_gzip_restore_required"] and not result["production_format_changed"]

def test_small_compression_gain_keeps_gzip():
    result=compression_advice({"source_bytes":1000,"gzip1_bytes":600,"zstd3_bytes":598,"zstd9_bytes":590})
    assert result["recommendation"]=="KEEP_GZIP1"

def test_report_protects_backup_and_marks_cache_review_only(tmp_path):
    backup=tmp_path/"backup"; backup.mkdir(); (backup/"b").write_bytes(b"x"*4096)
    cache=tmp_path/"cache"; cache.mkdir(); (cache/"c").write_bytes(b"y"*4096)
    report=build_report(scopes={"local_backups":backup,"npm_npx_cache":cache},
        disk={"pressure":"WARN","free_percent":14},
        now=datetime(2026,11,15,tzinfo=timezone.utc))
    assert report["inventory"]["local_backups"]["policy"]=="PROTECTED_KEEP"
    assert report["inventory"]["npm_npx_cache"]["policy"]=="REGENERABLE_REVIEW_ONLY"
    assert report["policy"]["deletion_authorized"] is False
    assert report["policy"]["compression_authorized"] is False

def test_disk_state_reports_inode_and_capacity_metrics():
    result=disk_state(Path("/"))
    assert result["total_bytes"]>0 and 0<=result["free_percent"]<=100
    assert result["pressure"] in {"OK","WARN","CRITICAL"}

def test_legacy_and_zstd_archive_formats_are_recognized(tmp_path):
    (tmp_path/"hes-offsite-core-20261115T043747Z.tar.gz.gpg").write_bytes(b"gzip")
    (tmp_path/"hes-offsite-core-20261116T043747Z.tar.zst.gpg").write_bytes(b"zstd")
    result=archive_inventory(tmp_path,"hes-offsite-core-")
    assert {x["format"] for x in result["archives"]}=={"gzip","zstd"}

def test_no_cleanup_or_retention_mutation_is_authorized(tmp_path):
    root=tmp_path/"protected"; root.mkdir()
    report=build_report(scopes={"evidence":root},disk={"pressure":"CRITICAL"})
    p=report["policy"]
    assert not p["deletion_authorized"] and not p["move_authorized"]
    assert not p["compression_authorized"] and not p["automatic_cleanup_timer_authorized"]
    assert report["inventory"]["evidence"]["action"]=="NONE"