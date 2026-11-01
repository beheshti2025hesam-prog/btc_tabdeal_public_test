import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import scripts.audit_gateio_soak_v2 as audit


def make_sample(seq, when, elapsed, *, ok=True, source="gateio_public_spot", symbol="BTC_USDT", age=60):
    return {
        "schema": "hes_gateio_soak_sample_v2", "sample": seq,
        "observed_at": when.isoformat(), "elapsed_seconds": elapsed,
        "source": source, "symbol": symbol, "ok": ok,
        "timeframes": {
            tf: {"bars": 240, "age_seconds": age,
                 "last_close_time": int(when.timestamp()) - age, "close": 80000.0}
            for tf in ("15m", "1h", "4h")
        },
        "services": {
            "hes-global-market-data-gateio.service": "active",
            "hes-global-market-data-gateio-1h.service": "active",
            "hes-global-market-data-gateio-4h.service": "active",
        },
    }


def make_records(*, bad_at=None, gap_at=None, wrong_tf_at=None, wrong_service_at=None):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    records = []
    elapsed = 0
    for seq in range(1, 1441):
        if gap_at == seq:
            elapsed += 120
        else:
            elapsed += 60 if seq > 1 else 0
        row = make_sample(seq, start + timedelta(seconds=elapsed), elapsed,
                          ok=bad_at != seq, age=50000 if wrong_tf_at == seq else 60)
        if wrong_service_at == seq:
            row["services"]["hes-global-market-data-gateio-1h.service"] = "inactive"
        records.append(row)
    finish = start + timedelta(seconds=elapsed + 60)
    records.append({
        "schema": "hes_gateio_soak_summary_v2", "finished_at": finish.isoformat(),
        "samples": 1440, "duration_seconds": elapsed + 60, "passed": True,
    })
    return records


def prepare_fixture(tmp: Path, records):
    root = tmp / "root"
    system_root = tmp / "system"
    root.mkdir()
    system_root.mkdir()
    paths = sorted(audit.REQUIRED_LINEAGE_PATHS)
    files = []
    for name in paths:
        target = audit._resolve_manifest_path(name, root, system_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = ("".join(json.dumps(row, sort_keys=True) + "\n" for row in records)).encode() if name == "data/forward/gateio_feed_soak_24h_v2.jsonl" else ("fixture:" + name).encode()
        target.write_bytes(content)
        files.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    manifest = {
        "schema": "hes_gateio_soak_runtime_lineage_v1",
        "source": "gateio_public_spot", "symbol": "BTC_USDT",
        "source_commit": "2e8d3859ef154b030e0965ad4479f3fad36ae4c0",
        "files": files,
    }
    manifest_path = root / "forward/gateio_soak_runtime_lineage_v1.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    manifest_path.write_bytes(raw)
    return root, system_root, manifest_path, root / "data/forward/gateio_feed_soak_24h_v2.jsonl", hashlib.sha256(raw).hexdigest()


class GateioSoakAuditTests(unittest.TestCase):
    def run_audit(self, records, tmp):
        root, system_root, manifest, log, digest = prepare_fixture(tmp, records)
        with patch.object(audit, "LINEAGE_MANIFEST_SHA256", digest):
            return audit.audit_log(log, root=root, system_root=system_root, manifest_path=manifest)

    def test_passes_only_full_continuous_24h_with_complete_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_audit(make_records(), Path(directory))
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["passed"])
        self.assertEqual(result["samples"], 1440)
        self.assertGreaterEqual(result["duration_seconds"], 86400)
        self.assertLessEqual(result["max_sample_gap_seconds"], 90)
        self.assertEqual(result["errors"], [])

    def test_incomplete_sample_count_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            records = make_records()[:100]
            result = self.run_audit(records, Path(directory))
        self.assertFalse(result["passed"])
        self.assertIn("SAMPLE_COUNT_BELOW_MINIMUM", result["errors"])

    def test_rejects_gap_over_90_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_audit(make_records(gap_at=500), Path(directory))
        self.assertFalse(result["passed"])
        self.assertIn("SAMPLE_GAP_INVALID", result["errors"])

    def test_rejects_any_bad_sample_even_if_summary_claims_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_audit(make_records(bad_at=9), Path(directory))
        self.assertFalse(result["passed"])
        self.assertIn("SAMPLE_NOT_OK:9", result["errors"])

    def test_checks_all_timeframes_and_required_services(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_audit(make_records(wrong_tf_at=4, wrong_service_at=5), Path(directory))
        self.assertFalse(result["passed"])
        self.assertIn("STALE_OR_FUTURE_CANDLE:4:1h", result["errors"])
        self.assertIn("SERVICE_NOT_ACTIVE:5", result["errors"])

    def test_rejects_missing_lineage_file(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            root, system_root, manifest, log, digest = prepare_fixture(tmp, make_records())
            missing = audit._resolve_manifest_path("/etc/systemd/system/hes-global-market-data-gateio.service", root, system_root)
            missing.unlink()
            with patch.object(audit, "LINEAGE_MANIFEST_SHA256", digest):
                result = audit.audit_log(log, root=root, system_root=system_root, manifest_path=manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any(x.startswith("LINEAGE_FILE_MISSING:") for x in result["errors"]))

    def test_rejects_mismatched_runtime_file_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            root, system_root, manifest, log, _ = prepare_fixture(tmp, make_records())
            target = root / "scripts/soak_gateio_feed_24h_v2.py"
            target.write_text("tampered", encoding="utf-8")
            raw = manifest.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            with patch.object(audit, "LINEAGE_MANIFEST_SHA256", digest):
                result = audit.audit_log(log, root=root, system_root=system_root, manifest_path=manifest)
        self.assertFalse(result["passed"])
        self.assertIn("LINEAGE_HASH_MISMATCH:scripts/soak_gateio_feed_24h_v2.py", result["errors"])

    def test_rejects_modified_manifest_even_if_its_entries_look_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            root, system_root, manifest, log, _ = prepare_fixture(tmp, make_records())
            manifest.write_text(manifest.read_text() + " ", encoding="utf-8")
            with patch.object(audit, "LINEAGE_MANIFEST_SHA256", "0" * 64):
                result = audit.audit_log(log, root=root, system_root=system_root, manifest_path=manifest)
        self.assertFalse(result["passed"])
        self.assertIn("LINEAGE_MANIFEST_SHA256_MISMATCH", result["errors"])


if __name__ == "__main__":
    unittest.main()
