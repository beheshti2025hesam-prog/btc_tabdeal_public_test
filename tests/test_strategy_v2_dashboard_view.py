from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import tempfile
from pathlib import Path
import unittest

from web.strategy_v2_dashboard_view import read_strategy_v2_dashboard, StrategyV2DashboardError


class StrategyV2DashboardViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.report = self.root / "report.json"
        self.journal = self.root / "journal.jsonl"
        self.now = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)
        self.write_report()
        self.write_journal()

    def tearDown(self):
        self.temp.cleanup()

    def market_data_provenance(self):
        return {
            "schema": "hes_market_data_batch_provenance_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "batch_limit": 240,
            "timeframes": {
                "15m": {"input_batch_sha256": "a" * 64, "candle_count": 240,
                        "last_closed_candle_time": 1793547900},
                "1h": {"input_batch_sha256": "b" * 64, "candle_count": 240,
                       "last_closed_candle_time": 1793547600},
                "4h": {"input_batch_sha256": "c" * 64, "candle_count": 240,
                       "last_closed_candle_time": 1793547000},
            },
        }

    def write_report(self, **changes):
        report = {
            "schema": "hes_strategy_policy_v2_forward_evaluation",
            "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            "updated_at": self.now.isoformat(),
            "closed_15m_candle_time": 1793547900,
            "final_gate_version": "hes-strategy-policy-final-gate-v1.0.0",
            "gate_pipeline_version": "hes-strategy-gate-pipeline-v1.0.1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "active_candidates": 0, "wins": 5, "losses": 9, "timeouts": 0,
            "resolved_win_rate_pct": None,
            "target_policy_status": "NOT_MET",
            "directional_candidates_blocked_until_gates_approved": True,
            "execution_enabled": False, "orders_placed": False,
            "market_data_provenance": self.market_data_provenance(),
            "latest_gate_evidence": {
                "source": "gateio_public_spot", "final_decision": "NO_TRADE",
                "market_data_provenance": self.market_data_provenance(),
                "structure": {"regime": "RANGE", "observed_at": self.now.isoformat()},
                "confirmation": {"reason_codes": ["NO_VALID_CANDIDATE"]},
                "risk": {"reason_codes": ["CONFIRMATION_NOT_VALID"]},
            },
        }
        report.update(changes)
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def write_journal(self):
        row = {
            "event_id": "hes-v2-BTC_USDT-15m-1793547900",
            "observed_at": self.now.isoformat(), "symbol": "BTC_USDT",
            "timeframe": "15m", "decision": "NO_TRADE", "direction": "NONE",
            "source": None, "evidence_source": "gateio_public_spot",
            "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            "outcome": None, "closed_at": None,
            "execution_enabled": False, "orders_placed": False,
            "no_trade_reason": "NO_VALID_CANDIDATE",
        }
        self.journal.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def read(self, **kwargs):
        return read_strategy_v2_dashboard(
            report_path=self.report, journal_path=self.journal, now=self.now, **kwargs
        )

    def test_projects_existing_v2_report_and_canonical_journal(self):
        result = self.read()
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["market_regime"], "RANGE")
        self.assertEqual(result["agent_version"], "hes-btcusdt-mtf-confirmed-breakout-v2.0.0")
        self.assertEqual(result["closed_15m_candle_time"], 1793547900)
        self.assertEqual(result["market_data_provenance"]["timeframes"]["15m"]["input_batch_sha256"], "a" * 64)
        self.assertEqual(result["final_gate_version"], "hes-strategy-policy-final-gate-v1.0.0")
        self.assertEqual(result["gate_pipeline_version"], "hes-strategy-gate-pipeline-v1.0.1")
        self.assertEqual(result["journal"]["decision_count"], 1)
        self.assertEqual(result["journal"]["events"][0]["source"], "gateio_public_spot")
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])
        self.assertFalse(result["outcomes_inferred"])

    def test_wrong_policy_version_fails_closed(self):
        self.write_report(policy_version="unapproved-policy")
        with self.assertRaisesRegex(StrategyV2DashboardError, "policy_version_mismatch"):
            self.read()

    def test_wrong_journal_source_fails_closed(self):
        row = json.loads(self.journal.read_text(encoding="utf-8"))
        row["evidence_source"] = "binance_public_spot"
        self.journal.write_text(json.dumps(row) + chr(10), encoding="utf-8")
        with self.assertRaisesRegex(StrategyV2DashboardError, "unexpected_source"):
            self.read()

    def test_wrong_journal_symbol_fails_closed(self):
        row = json.loads(self.journal.read_text(encoding="utf-8"))
        row["symbol"] = "ETH_USDT"
        self.journal.write_text(json.dumps(row) + chr(10), encoding="utf-8")
        with self.assertRaisesRegex(StrategyV2DashboardError, "unexpected_symbol"):
            self.read()

    def test_wrong_journal_policy_version_fails_closed(self):
        row = json.loads(self.journal.read_text(encoding="utf-8"))
        row["policy_version"] = "unapproved-policy"
        self.journal.write_text(json.dumps(row) + chr(10), encoding="utf-8")
        with self.assertRaisesRegex(StrategyV2DashboardError, "unexpected_policy_version"):
            self.read()

    def test_journal_execution_flags_fail_closed(self):
        row = json.loads(self.journal.read_text(encoding="utf-8"))
        row["orders_placed"] = bool(1)
        self.journal.write_text(json.dumps(row) + chr(10), encoding="utf-8")
        with self.assertRaisesRegex(StrategyV2DashboardError, "execution_boundary_violation"):
            self.read()

    def test_stale_report_fails_closed(self):
        self.write_report(updated_at=(self.now - timedelta(seconds=1801)).isoformat())
        with self.assertRaisesRegex(StrategyV2DashboardError, "stale_or_future"):
            self.read()

    def test_stale_market_evidence_fails_closed_even_if_report_is_fresh(self):
        gate = self.read()["latest_gate_evidence"]
        gate["structure"]["observed_at"] = (self.now - timedelta(seconds=1801)).isoformat()
        self.write_report(latest_gate_evidence=gate)
        with self.assertRaisesRegex(StrategyV2DashboardError, "market_evidence_stale_or_future"):
            self.read()

    def test_live_chart_batch_must_match_strategy_report(self):
        current = self.market_data_provenance()
        current["timeframes"]["15m"]["input_batch_sha256"] = "d" * 64
        with self.assertRaisesRegex(StrategyV2DashboardError, "market_data_batch_mismatch"):
            self.read(current_market_data_provenance=current)

    def test_missing_batch_provenance_fails_closed(self):
        self.write_report(market_data_provenance=None)
        with self.assertRaisesRegex(StrategyV2DashboardError, "market_data_provenance_missing"):
            self.read()

    def test_gate_batch_provenance_must_match_report(self):
        gate = self.read()["latest_gate_evidence"]
        gate["market_data_provenance"]["timeframes"]["15m"]["input_batch_sha256"] = "d" * 64
        self.write_report(latest_gate_evidence=gate)
        with self.assertRaisesRegex(StrategyV2DashboardError, "gate_market_data_provenance_mismatch"):
            self.read()

    def test_invalid_batch_digest_fails_closed(self):
        provenance = self.market_data_provenance()
        provenance["timeframes"]["1h"]["input_batch_sha256"] = "not-a-sha256"
        gate = self.read()["latest_gate_evidence"]
        gate["market_data_provenance"] = provenance
        self.write_report(market_data_provenance=provenance, latest_gate_evidence=gate)
        with self.assertRaisesRegex(StrategyV2DashboardError, "provenance_entry_invalid:1h"):
            self.read()

    def test_15m_batch_close_must_match_report_candle(self):
        provenance = self.market_data_provenance()
        provenance["timeframes"]["15m"]["last_closed_candle_time"] += 900
        gate = self.read()["latest_gate_evidence"]
        gate["market_data_provenance"] = provenance
        self.write_report(market_data_provenance=provenance, latest_gate_evidence=gate)
        with self.assertRaisesRegex(StrategyV2DashboardError, "provenance_candle_mismatch"):
            self.read()

    def test_wrong_market_source_fails_closed(self):
        self.write_report(source="binance_public_spot")
        with self.assertRaisesRegex(StrategyV2DashboardError, "market_identity"):
            self.read()

    def test_live_execution_flag_fails_closed(self):
        self.write_report(execution_enabled=True)
        with self.assertRaisesRegex(StrategyV2DashboardError, "execution_boundary"):
            self.read()

    def test_directional_gate_must_remain_locked(self):
        self.write_report(directional_candidates_blocked_until_gates_approved=False)
        with self.assertRaisesRegex(StrategyV2DashboardError, "directional_gate"):
            self.read()

    def test_non_no_trade_decision_fails_closed(self):
        gate = self.read()["latest_gate_evidence"]
        gate["final_decision"] = "LONG"
        self.write_report(latest_gate_evidence=gate)
        with self.assertRaisesRegex(StrategyV2DashboardError, "latest_gate_evidence"):
            self.read()

    def test_invalid_canonical_journal_fails_closed(self):
        self.journal.write_text("{broken}\n", encoding="utf-8")
        with self.assertRaisesRegex(StrategyV2DashboardError, "canonical_journal_invalid"):
            self.read()

    def test_missing_journal_fails_closed(self):
        self.journal.unlink()
        with self.assertRaisesRegex(StrategyV2DashboardError, "canonical_journal_invalid"):
            self.read()


if __name__ == "__main__":
    unittest.main()
