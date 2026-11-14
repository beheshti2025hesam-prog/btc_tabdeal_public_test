from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from core.paper.strategy_v2_execution_gate import (
    EXPECTED_RECOVERY_CANDIDATE_HEAD,
    PaperExecutionGateV1,
    RECOVERY_SCHEMA,
    RECOVERY_CANDIDATE_1M_SERVICE,
    RECOVERY_MARKET_DATA_ROOT,
    RECOVERY_REQUIRED_SERVICES,
    _canonical_hash,
    verify_gateio_1m_recovery_evidence,
)


class PaperExecutionGateTests(unittest.TestCase):
    def _active(self):
        flags = {
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "historical_performance_tuning_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        }
        rules = {
            "status": "ACTIVE",
            "historical_inputs_allowed": False,
            "future_outcome_leakage_allowed": False,
            "execution_enabled": False,
        }
        return flags, rules

    def _ready_args(self):
        policy, ruleset = self._active()
        return {
            "policy": policy,
            "ruleset": ruleset,
            "data_live": True,
            "structure_safe": True,
            "sequence_safe": True,
            "clock_safe": True,
            "health_safe": True,
            "recovery_safe": True,
            "proposal_decision": "LONG",
            "confirmation_state": "CONFIRMED_LONG",
            "risk_state": "RISK_APPROVED",
            "precision_entry_ready": True,
        }

    def test_ready_paper_intent_never_calls_or_authorizes_execution(self):
        result = PaperExecutionGateV1().evaluate(**self._ready_args())
        payload = result.as_dict()
        self.assertTrue(result.ready)
        self.assertEqual(result.status, "READY_FOR_PAPER_SIMULATION")
        self.assertEqual(result.paper_intent, "ENTER_LONG")
        self.assertFalse(payload["execution_enabled"])
        self.assertFalse(payload["orders_placed"])
        self.assertFalse(payload["capital_mutated"])
        self.assertFalse(payload["venue_adapter_called"])
        self.assertFalse(payload["position_created"])

    def test_missing_activation_and_recovery_evidence_fail_closed(self):
        args = self._ready_args()
        args["policy"] = {}
        args["ruleset"] = {}
        args["recovery_safe"] = False
        result = PaperExecutionGateV1().evaluate(**args)
        self.assertFalse(result.ready)
        self.assertEqual(result.status, "BLOCKED")
        self.assertIn("POLICY_NOT_ACTIVE", result.reason_codes)
        self.assertIn("RULESET_NOT_ACTIVE", result.reason_codes)
        self.assertIn("INTEGRATION_GATE_BLOCKED:RECOVERY_UNSAFE", result.reason_codes)
        self.assertIsNone(result.paper_intent)

    def test_wrong_confirmation_risk_or_stale_one_minute_feed_blocks(self):
        args = self._ready_args()
        args["confirmation_state"] = "CONFIRMED_SHORT"
        args["risk_state"] = "RISK_REJECTED"
        args["precision_entry_ready"] = False
        result = PaperExecutionGateV1().evaluate(**args)
        self.assertFalse(result.ready)
        self.assertIn("CONFIRMATION_NOT_APPROVED_FOR_DIRECTION", result.reason_codes)
        self.assertIn("RISK_GATE_NOT_APPROVED", result.reason_codes)
        self.assertIn("PRECISION_ENTRY_1M_FEED_NOT_READY", result.reason_codes)

    def test_unreached_risk_specialist_is_not_misreported_as_a_rejection(self):
        args = self._ready_args()
        args["confirmation_state"] = "UNCONFIRMED"
        args["risk_state"] = "NOT_EVALUATED"
        result = PaperExecutionGateV1().evaluate(**args)
        self.assertFalse(result.ready)
        self.assertIn("RISK_GATE_NOT_EVALUATED_UPSTREAM_BLOCKED", result.reason_codes)
        self.assertNotIn("RISK_GATE_NOT_APPROVED", result.reason_codes)

    def test_live_execution_or_historical_leakage_never_passes(self):
        args = self._ready_args()
        args["execution_enabled"] = True
        args["historical_inputs_allowed"] = True
        result = PaperExecutionGateV1().evaluate(**args)
        self.assertFalse(result.ready)
        self.assertIn("LIVE_EXECUTION_FORBIDDEN", result.reason_codes)
        self.assertIn("HISTORICAL_INPUTS_FORBIDDEN", result.reason_codes)

    def test_recovery_evidence_requires_official_release_bound_soak_and_artifact_hashes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = root / "releases" / EXPECTED_RECOVERY_CANDIDATE_HEAD
            (release / "scripts").mkdir(parents=True)
            (release / "forward").mkdir()
            soak_script = release / "scripts/soak_gateio_feed_24h_v2.py"
            reader_script = release / "forward/global_market_data_reader_v1.py"
            collector_script = release / "scripts/run_global_market_data_gateio_service.py"
            collector_module = release / "forward/global_market_data_gateio_v1.py"
            soak_script.write_text("# immutable fixture soak script\n", encoding="utf-8")
            reader_script.write_text("# immutable fixture market reader\n", encoding="utf-8")
            collector_script.write_text("# immutable fixture collector entry\n", encoding="utf-8")
            collector_module.write_text("# immutable fixture collector module\n", encoding="utf-8")
            script_hash = sha256(soak_script.read_bytes()).hexdigest()
            reader_hash = sha256(reader_script.read_bytes()).hexdigest()
            collector_script_hash = sha256(collector_script.read_bytes()).hexdigest()
            collector_module_hash = sha256(collector_module.read_bytes()).hexdigest()
            manifest = {
                "commit_sha": EXPECTED_RECOVERY_CANDIDATE_HEAD,
                "file_count": 4,
                "files": [
                    {"path": "scripts/soak_gateio_feed_24h_v2.py", "sha256": script_hash},
                    {"path": "forward/global_market_data_reader_v1.py", "sha256": reader_hash},
                    {"path": "scripts/run_global_market_data_gateio_service.py", "sha256": collector_script_hash},
                    {"path": "forward/global_market_data_gateio_v1.py", "sha256": collector_module_hash},
                ],
            }
            manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
            manifest_path = release / "HES_RELEASE_MANIFEST_v1.json"
            sidecar_path = release / "HES_RELEASE_MANIFEST_v1.sha256"
            manifest_path.write_bytes(manifest_bytes)
            manifest_hash = sha256(manifest_bytes).hexdigest()
            sidecar_path.write_text(f"{manifest_hash}  HES_RELEASE_MANIFEST_v1.json\n", encoding="ascii")
            for item in release.rglob("*"):
                if item.is_file():
                    item.chmod(0o444)
            for item in sorted((x for x in release.rglob("*") if x.is_dir()), reverse=True):
                item.chmod(0o555)
            release.chmod(0o555)

            now = datetime(2026, 11, 13, 18, 0, 30, tzinfo=timezone.utc)
            market_root = root / RECOVERY_MARKET_DATA_ROOT
            market_forward = market_root / "data/forward"
            market_forward.mkdir(parents=True)
            candidate_ledger = market_forward / "global_market_candles_1m_v1.jsonl"
            candidate_ledger.write_text("fixture candidate ledger\n", encoding="utf-8")
            wrapper_path = market_root / "run_candidate_soak.py"
            wrapper_text = "\n".join([
                "import runpy",
                f"script = {str(release / 'scripts/soak_gateio_feed_24h_v2.py')!r}",
                "ns = runpy.run_path(script)",
                'g = ns["main"].__globals__',
                'g["SERVICES"] = (',
                f"    {'hes-global-market-data-gateio.service'!r},",
                f"    {'hes-global-market-data-gateio-1m.service'!r},",
                f"    {'hes-global-market-data-gateio-1m-integrity.timer'!r},",
                f"    {RECOVERY_CANDIDATE_1M_SERVICE!r},",
                f"    {'hes-global-market-data-gateio-1h.service'!r},",
                f"    {'hes-global-market-data-gateio-4h.service'!r},",
                ")",
                'raise SystemExit(ns["main"]())',
                "",
            ])
            wrapper_path.write_text(wrapper_text, encoding="utf-8")
            collector_manifest_path = market_root / "candidate_collector_unit_manifest.json"
            collector_manifest = {
                "schema": "hes.gateio_1m_candidate_collector_unit.v1",
                "unit_name": RECOVERY_CANDIDATE_1M_SERVICE,
                "captured_at_utc": now.isoformat(),
                "candidate_root": str(market_root),
                "properties": {
                    "Id": RECOVERY_CANDIDATE_1M_SERVICE,
                    "ActiveState": "active",
                    "SubState": "running",
                    "User": "sentinelx",
                    "Group": "sentinelx",
                    "WorkingDirectory": str(release),
                    "ExecStart": f"{{ path=/opt/hes-trade-agent/.venv/bin/python ; argv[]=/opt/hes-trade-agent/.venv/bin/python -u {collector_script} }}",
                    "Environment": f"PYTHONUNBUFFERED=1 HES_GLOBAL_CANDLES_INTERVAL=1m HES_GLOBAL_CANDLES_OUTPUT={candidate_ledger}",
                    "ReadWritePaths": str(market_forward),
                    "Restart": "always",
                    "RestartUSec": "5s",
                },
            }
            collector_manifest_path.write_text(json.dumps(collector_manifest, sort_keys=True), encoding="utf-8")

            artifact_dir = root / "data/forward/gateio_1m_recovery_24h"
            artifact_dir.mkdir(parents=True)
            run_id = "fixture-official-soak-run"
            services = sorted(RECOVERY_REQUIRED_SERVICES)
            samples = []
            for i in range(1441):
                observed = now + timedelta(seconds=i * 60)
                ts = int(observed.timestamp())
                frames = {}
                for tf, seconds, bars, close in (
                    ("1m", 60, 5000, 100.0),
                    ("15m", 900, 1191, 101.0),
                    ("1h", 3600, 983, 102.0),
                    ("4h", 14400, 620, 103.0),
                ):
                    last_close = ts // seconds * seconds
                    frames[tf] = {
                        "bars": bars,
                        "last_close_time": last_close,
                        "age_seconds": ts - last_close,
                        "close": close,
                    }
                samples.append({
                    "schema": "hes_gateio_soak_sample_v3",
                    "run_id": run_id,
                    "sample": i + 1,
                    "observed_at": observed.isoformat(),
                    "elapsed_seconds": i * 60,
                    "code_release_id": EXPECTED_RECOVERY_CANDIDATE_HEAD,
                    "release_manifest_sha256": manifest_hash,
                    "soak_script_sha256": script_hash,
                    "execution_enabled": False,
                    "orders_placed": False,
                    "source": "gateio_public_spot",
                    "symbol": "BTC_USDT",
                    "timeframes": frames,
                    "services": {name: "active" for name in services},
                    "ok": True,
                })
            finished = now + timedelta(seconds=86400)
            final_close = int(finished.timestamp()) // 60 * 60
            first_open = final_close - 240 * 60
            candle_rows = []
            for i in range(240):
                open_time = first_open + i * 60
                candle_rows.append({
                    "schema": "hes_global_candle_v1",
                    "source": "gateio_public_spot",
                    "symbol": "BTC_USDT",
                    "timeframe": "1m",
                    "open_time": open_time,
                    "close_time": open_time + 60,
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.5,
                    "volume": 10.0,
                    "quote_volume": 1000.0,
                    "closed": True,
                })
            candle_path = artifact_dir / "candles_1m.jsonl"
            candle_path.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in candle_rows), encoding="utf-8")
            candle_hash = sha256(candle_path.read_bytes()).hexdigest()
            sample_summary = {
                "schema": "hes_gateio_soak_summary_v3",
                "run_id": run_id,
                "code_release_id": EXPECTED_RECOVERY_CANDIDATE_HEAD,
                "release_manifest_sha256": manifest_hash,
                "soak_script_sha256": script_hash,
                "finished_at": finished.isoformat(),
                "samples": len(samples),
                "duration_seconds": 86400,
                "timeframes": ["1m", "15m", "1h", "4h"],
                "services": services,
                "passed": True,
                "execution_enabled": False,
                "orders_placed": False,
            }
            sample_path = artifact_dir / "soak.jsonl"
            sample_path.write_text(
                "".join(json.dumps(x, sort_keys=True) + "\n" for x in samples)
                + json.dumps(sample_summary, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            collector_path = artifact_dir / "collector_1m.log"
            collector_path.write_text("HES_GLOBAL_MARKET_START\nHES_GLOBAL_MARKET_WS_SUBSCRIBED\n", encoding="utf-8")
            wrapper_artifact = artifact_dir / "soak_wrapper.py"
            wrapper_artifact.write_text(wrapper_path.read_text(encoding="utf-8"), encoding="utf-8")
            manifest_artifact = artifact_dir / "candidate_collector_manifest.json"
            manifest_artifact.write_text(collector_manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
            for item in artifact_dir.iterdir():
                item.chmod(0o444)
            artifact_dir.chmod(0o555)
            artifacts = {
                "candle_ledger": {"path": "data/forward/gateio_1m_recovery_24h/candles_1m.jsonl",
                                  "sha256": candle_hash},
                "sample_ledger": {"path": "data/forward/gateio_1m_recovery_24h/soak.jsonl",
                                  "sha256": sha256(sample_path.read_bytes()).hexdigest()},
                "collector_log": {"path": "data/forward/gateio_1m_recovery_24h/collector_1m.log",
                                  "sha256": sha256(collector_path.read_bytes()).hexdigest()},
                "soak_wrapper": {"path": "data/forward/gateio_1m_recovery_24h/soak_wrapper.py",
                                 "sha256": sha256(wrapper_artifact.read_bytes()).hexdigest()},
                "candidate_collector_manifest": {"path": "data/forward/gateio_1m_recovery_24h/candidate_collector_manifest.json",
                                                  "sha256": sha256(manifest_artifact.read_bytes()).hexdigest()},
            }
            payload = {
                "schema": RECOVERY_SCHEMA,
                "status": "PASS",
                "candidate_head": EXPECTED_RECOVERY_CANDIDATE_HEAD,
                "run_id": run_id,
                "started_at": now.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_seconds": 86400,
                "samples": 1441,
                "new_closed_candles": 1440,
                "max_observed_candle_age_seconds": 30,
                "release_manifest_sha256": manifest_hash,
                "soak_script_sha256": script_hash,
                "collector_script_sha256": collector_script_hash,
                "collector_module_sha256": collector_module_hash,
                "candidate_market_data_root": RECOVERY_MARKET_DATA_ROOT,
                "candidate_collector_service": RECOVERY_CANDIDATE_1M_SERVICE,
                "final_stats": {
                    "rows": len(candle_rows),
                    "last_open_time": candle_rows[-1]["open_time"],
                    "last_close_time": candle_rows[-1]["close_time"],
                    "age_seconds": 30,
                    "gaps": 0,
                    "duplicates": 0,
                    "sha256": candle_hash,
                },
                "artifacts": artifacts,
            }
            payload["evidence_sha256"] = _canonical_hash(payload)
            evidence = root / "data/forward/gateio_1m_recovery_24h_evidence.json"
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            evidence.chmod(0o444)
            result = verify_gateio_1m_recovery_evidence(
                evidence, data_root=root, now=finished + timedelta(minutes=1)
            )
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(result["candidate_head"], EXPECTED_RECOVERY_CANDIDATE_HEAD)
            self.assertEqual(result["new_closed_candles"], 1440)

            payload["candidate_head"] = "bad-head"
            payload["evidence_sha256"] = _canonical_hash({k: v for k, v in payload.items() if k != "evidence_sha256"})
            evidence.chmod(0o644)
            evidence.write_text(json.dumps(payload), encoding="utf-8")
            evidence.chmod(0o444)
            rejected = verify_gateio_1m_recovery_evidence(
                evidence, data_root=root, now=finished + timedelta(minutes=1)
            )
            self.assertEqual(rejected["status"], "BLOCKED")
            self.assertEqual(rejected["reason"], "RECOVERY_CANDIDATE_HEAD_MISMATCH")

if __name__ == "__main__":
    unittest.main()
