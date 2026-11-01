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

    def write_report(self, **changes):
        report = {
            "schema": "hes_strategy_policy_v2_forward_evaluation",
            "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            "updated_at": self.now.isoformat(),
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "active_candidates": 0, "wins": 5, "losses": 9, "timeouts": 0,
            "resolved_win_rate_pct": None,
            "target_policy_status": "NOT_MET",
            "directional_candidates_blocked_until_gates_approved": True,
            "execution_enabled": False, "orders_placed": False,
            "latest_gate_evidence": {
                "source": "gateio_public_spot", "final_decision": "NO_TRADE",
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
            "evidence_source": "gateio_public_spot", "outcome": None, "closed_at": None,
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
        self.assertEqual(result["journal"]["decision_count"], 1)
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])
        self.assertFalse(result["outcomes_inferred"])

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
