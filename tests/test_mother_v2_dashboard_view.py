from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import tempfile
from pathlib import Path
import unittest

from web.mother_v2_dashboard_view import read_mother_v2_dashboard, MotherV2DashboardError


class MotherV2DashboardViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.report = self.root / "report.json"
        self.journal = self.root / "journal.jsonl"
        self.now = datetime(2026, 11, 1, 16, 2, tzinfo=timezone.utc)
        self.candle_time = 1793548800
        self.write_report()
        self.write_journal()

    def market_data_provenance(self):
        return {
            "schema": "hes_market_data_batch_provenance_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "batch_limit": 240,
            "timeframes": {
                "15m": {"input_batch_sha256": "a" * 64, "candle_count": 240,
                        "last_closed_candle_time": self.candle_time},
                "1h": {"input_batch_sha256": "b" * 64, "candle_count": 240,
                       "last_closed_candle_time": 1793545200},
                "4h": {"input_batch_sha256": "c" * 64, "candle_count": 240,
                       "last_closed_candle_time": 1793534400},
            },
        }

    def write_report(self, *, confirmation_state="UNCONFIRMED", risk_state="RISK_REJECTED",
                     final_decision="NO_TRADE", updated_at=None, execution_enabled=False):
        observed = datetime(2026, 11, 1, 16, 0, tzinfo=timezone.utc)
        report = {
            "schema": "hes_strategy_policy_v2_forward_evaluation",
            "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            "updated_at": updated_at if isinstance(updated_at, str) else (updated_at or observed + timedelta(minutes=1)).isoformat(),
            "closed_15m_candle_time": self.candle_time,
            "final_gate_version": "hes-strategy-policy-final-gate-v1.0.0",
            "gate_pipeline_version": "hes-strategy-gate-pipeline-v1.0.1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "active_candidates": 0, "wins": 0, "losses": 0, "timeouts": 0,
            "resolved_win_rate_pct": None,
            "target_policy_status": "UNSET_PENDING_APPROVED_PROJECT_DECISION",
            "directional_candidates_blocked_until_gates_approved": True,
            "execution_enabled": execution_enabled, "orders_placed": False,
            "market_data_provenance": self.market_data_provenance(),
            "latest_gate_evidence": {
                "pipeline_version": "hes-strategy-gate-pipeline-v1.0.1",
                "source": "gateio_public_spot", "symbol": "BTC_USDT", "timeframe": "15m",
                "final_decision": final_decision,
                "market_data_provenance": self.market_data_provenance(),
                "structure": {
                    "observed_at": observed.isoformat(), "status": "OBSERVED",
                    "regime": "RANGE", "labels": ["LH", "LL"], "events": [],
                },
                "confirmation": {
                    "state": confirmation_state,
                    "reason_codes": [] if confirmation_state.startswith("CONFIRMED_") else ["REQUIRED_CHECK_FAILED"],
                    "checks": [{"name": "candidate_valid", "state": "PASS",
                                "evidence_ref": "policy:NO_TRADE", "observed_at": observed.isoformat()}],
                },
                "risk": {
                    "state": risk_state,
                    "reason_codes": [] if risk_state == "RISK_APPROVED" else ["CONFIRMATION_NOT_VALID"],
                    "checks": [{"name": "execution_disabled", "state": "PASS",
                                "evidence_ref": "safety:live_execution_disabled", "observed_at": observed.isoformat()}],
                },
                "execution_enabled": False, "orders_placed": False,
            },
        }
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def write_journal(self, *, event_id=None, confirmation_state="UNCONFIRMED",
                      risk_state="RISK_REJECTED", decision="NO_TRADE", observed_at=None,
                      execution_enabled=False):
        row = {
            "event_id": event_id or f"hes-v2-BTC_USDT-15m-{self.candle_time}",
            "observed_at": (observed_at or datetime(2026, 11, 1, 16, 0, 5, tzinfo=timezone.utc)).isoformat(),
            "symbol": "BTC_USDT", "timeframe": "15m", "decision": decision, "direction": "NONE",
            "evidence_source": "gateio_public_spot", "source": "gateio_public_spot",
            "policy_version": "hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            "market_regime": "RANGE", "signal_state": "NO_TRADE",
            "confirmation_state": confirmation_state, "risk_state": risk_state,
            "no_trade_reason": "NO_CONFIRMED_20_BAR_BREAKOUT",
            "outcome": None, "closed_at": None,
            "execution_enabled": execution_enabled, "orders_placed": False,
        }
        self.journal.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def read(self):
        return read_mother_v2_dashboard(
            report_path=str(self.report), journal_path=str(self.journal), now=self.now
        )

    def test_unconfirmed_gate_is_audited_as_no_trade_and_witnessed(self):
        result = self.read()
        self.assertEqual(result["status"], "BLOCKED_GATE")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual([x["agent"] for x in result["stages"]],
                         ["data_quality", "market_structure", "signal", "confirmation"])
        self.assertTrue(result["witness"]["verified"])
        self.assertEqual(result["market_data_provenance"]["timeframes"]["15m"]["input_batch_sha256"], "a" * 64)
        signal_stage = next(stage for stage in result["stages"] if stage["agent"] == "signal")
        self.assertIn("market_batch:15m:sha256:" + "a" * 64, signal_stage["evidence_refs"])
        for stage in result["stages"]:
            for timeframe, digest in (("15m", "a" * 64), ("1h", "b" * 64), ("4h", "c" * 64)):
                self.assertIn(f"market_batch:{timeframe}:sha256:{digest}", stage["evidence_refs"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])

    def test_risk_veto_is_reached_only_after_confirmation_passes(self):
        self.write_report(confirmation_state="CONFIRMED_LONG", risk_state="RISK_REJECTED")
        self.write_journal(confirmation_state="CONFIRMED_LONG", risk_state="RISK_REJECTED")
        result = self.read()
        self.assertEqual(result["status"], "BLOCKED_RISK_VETO")
        self.assertEqual([x["agent"] for x in result["stages"]],
                         ["data_quality", "market_structure", "signal", "confirmation", "risk"])
        self.assertTrue(result["witness"]["verified"])
        self.assertFalse(result["execution_enabled"])

    def test_all_observation_gates_can_finish_without_authorizing_execution(self):
        self.write_report(confirmation_state="CONFIRMED_LONG", risk_state="RISK_APPROVED")
        self.write_journal(confirmation_state="CONFIRMED_LONG", risk_state="RISK_APPROVED")
        result = self.read()
        self.assertEqual(result["status"], "OBSERVATION_ONLY")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(len(result["stages"]), 7)
        self.assertTrue(result["witness"]["verified"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])

    def test_missing_matching_journal_event_fails_closed(self):
        self.write_journal(event_id="different-event")
        with self.assertRaisesRegex(MotherV2DashboardError, "matching_v2_decision_event_missing"):
            self.read()

    def test_report_journal_specialist_mismatch_fails_closed(self):
        self.write_journal(confirmation_state="CONFIRMED_LONG")
        with self.assertRaisesRegex(MotherV2DashboardError, "v2_specialist_journal_mismatch"):
            self.read()

    def test_directional_or_execution_flag_drift_fails_closed(self):
        self.write_report(execution_enabled=True)
        with self.assertRaisesRegex(MotherV2DashboardError, "strategy_v2_evidence_blocked"):
            self.read()

    def test_stale_report_fails_closed(self):
        self.write_report(updated_at=(self.now - timedelta(hours=1)).isoformat())
        with self.assertRaisesRegex(MotherV2DashboardError, "strategy_v2_evidence_blocked"):
            self.read()


if __name__ == "__main__":
    unittest.main()
