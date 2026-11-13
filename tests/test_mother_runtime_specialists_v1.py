from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from forward.global_market_data_reader_v1 import MarketDataRejected
from forward.strategy_policy_v2 import PolicyDecision, POLICY_VERSION
from web.mother_runtime_dashboard_view import read_mother_runtime_dashboard
import core.orchestration.mother_runtime_specialists_v1 as runtime


def _rows(timeframe: str, seconds: int, now: datetime, count: int = 240):
    last_close = (int(now.timestamp()) // seconds) * seconds
    rows = []
    for index in range(count):
        close_time = last_close - (count - index - 1) * seconds
        open_time = close_time - seconds
        price = 100.0 + (index % 9) / 10
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": timeframe,
            "open_time": open_time,
            "close_time": close_time,
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price + 0.2,
            "volume": 10.0,
            "quote_volume": 1000.0,
            "closed": True,
            "observed_at": now.isoformat(),
        })
    return rows


class MotherRuntimeSpecialistsTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2026, 11, 13, 15, 10, 50, tzinfo=timezone.utc)
        self.data = {
            "schema": "hes_global_market_input_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "observed_at": self.now.isoformat(),
            "timeframes": {
                "15m": _rows("15m", 900, self.now),
                "1h": _rows("1h", 3600, self.now),
                "4h": _rows("4h", 14400, self.now),
            },
        }
        self.one_minute = _rows("1m", 60, self.now)

    def _run(self, *, confirmation_state="CONFIRMED_LONG", risk_state="RISK_APPROVED",
             one_minute_ready=True):
        proposal = PolicyDecision(
            POLICY_VERSION, "LONG", "LONG", 95, 100.0, 98.0, 106.0, 3.0,
            ("TEST_DIRECTIONAL_PROPOSAL",), {"policy": "PASS"},
        )
        structure = {
            "observed_at": self.now.isoformat(),
            "status": "OBSERVED",
            "regime": "UPTREND",
            "labels": ["HH", "HL"],
            "swing_count": 4,
            "last_swing_high": "110",
            "last_swing_low": "98",
            "events": ["BOS_BULLISH"],
            "policy_note": "test fixture",
        }
        confirmation = SimpleNamespace(
            state=confirmation_state,
            reason_codes=() if confirmation_state == "CONFIRMED_LONG" else ("TEST_CONFIRMATION_VETO",),
            passed_count=3 if confirmation_state == "CONFIRMED_LONG" else 1,
            required_count=3,
            checks=[],
        )
        risk = SimpleNamespace(
            state=risk_state,
            reason_codes=() if risk_state == "RISK_APPROVED" else ("TEST_RISK_VETO",),
            checks=[],
        )
        final_gate = SimpleNamespace(as_dict=lambda: {
            "gate_version": "hes-strategy-policy-final-gate-v1.0.0",
            "proposal": proposal.as_dict(),
            "decision": "NO_TRADE",
            "direction": "NONE",
            "reasons": ["FINAL_POLICY_APPROVAL_REQUIRED"],
            "execution_enabled": False,
            "orders_placed": False,
        })
        journal = {
            "schema": "hes.trade_journal_view.v1",
            "status": "VERIFIED",
            "count": 1,
            "decision_count": 1,
            "events": [{
                "event_id": "fixture-event-1",
                "decision": "NO_TRADE",
                "event_sha256": "a" * 64,
            }],
        }
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime, "load_market_input", return_value=self.data))
            if one_minute_ready:
                stack.enter_context(patch.object(runtime, "read_closed_candles", return_value=self.one_minute))
            else:
                stack.enter_context(patch.object(runtime, "read_closed_candles",
                                                 side_effect=MarketDataRejected("CANDLE_FEED_STALE")))
            stack.enter_context(patch.object(runtime, "inspect_structure", return_value=structure))
            stack.enter_context(patch.object(runtime, "snapshot", side_effect=lambda tf, rows: {
                "timeframe": tf, "bars": len(rows), "candle_closed": True,
                "close": 100.0, "ema50": 99.0, "ema200": 98.0, "atr14": 1.0,
                "rsi14": 60.0, "mfi14": 60.0, "vwap20": 99.0,
            }))
            stack.enter_context(patch.object(runtime, "evaluate_strategy", return_value=proposal))
            confirm_mock = stack.enter_context(patch.object(
                runtime, "evaluate_confirmation_evidence",
                return_value={"confirmation": confirmation, "candidate": None},
            ))
            risk_mock = stack.enter_context(patch.object(
                runtime, "evaluate_risk_evidence", return_value={"risk": risk},
            ))
            stack.enter_context(patch.object(runtime, "enforce_final_gates", return_value=final_gate))
            stack.enter_context(patch.object(runtime, "read_decision_journal", return_value=journal))
            result = read_mother_runtime_dashboard(
                data_root=self.temp.name,
                now=self.now,
                journal_path=Path(self.temp.name) / "journal.jsonl",
            )
        return result, confirm_mock, risk_mock

    def test_all_seven_runtime_specialists_execute_independently(self):
        result, confirm_mock, risk_mock = self._run()
        self.assertEqual(result["runtime_mode"], "LIVE_DATA_RUNTIME_SPECIALISTS")
        self.assertEqual(result["status"], "OBSERVATION_ONLY")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["registered_count"], 7)
        self.assertEqual(result["executed_count"], 7)
        self.assertEqual(result["executed_specialists"], [
            "data_quality", "market_structure", "signal", "confirmation",
            "risk", "decision", "evaluation",
        ])
        self.assertEqual(confirm_mock.call_count, 1)
        self.assertEqual(risk_mock.call_count, 1)
        self.assertTrue(result["witness"]["verified"])
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])
        self.assertFalse(result["journal_write"])
        self.assertFalse(result["outcomes_inferred"])
        self.assertTrue(result["precision_entry"]["direction_authority"] is False)
        self.assertEqual(result["sequence_validation"]["basis"], "CANDLE_OPEN_TIME_CONTINUITY")
        self.assertFalse(result["sequence_validation"]["trade_sequence_used"])
        self.assertEqual(result["sequence_validation"]["trade_sequence_semantics"], "UNKNOWN_NOT_USED")
        self.assertEqual(result["paper_execution_gate"]["status"], "BLOCKED")
        self.assertIn("POLICY_NOT_ACTIVE", result["paper_execution_gate"]["reason_codes"])
        self.assertIn("INTEGRATION_GATE_BLOCKED:RECOVERY_UNSAFE", result["paper_execution_gate"]["reason_codes"])

    def test_confirmation_veto_does_not_suppress_risk_decision_or_evaluation(self):
        result, confirm_mock, risk_mock = self._run(confirmation_state="UNCONFIRMED")
        self.assertEqual(result["status"], "BLOCKED_GATE")
        self.assertEqual(result["decision"], "NO_TRADE")
        self.assertEqual(result["registered_count"], 7)
        self.assertEqual(result["executed_count"], 7)
        self.assertEqual(result["executed_specialists"], [
            "data_quality", "market_structure", "signal", "confirmation",
            "risk", "decision", "evaluation",
        ])
        self.assertEqual(confirm_mock.call_count, 1)
        risk_mock.assert_called_once()
        self.assertTrue(result["witness"]["verified"])
        self.assertFalse(result["execution_enabled"])

    def test_missing_one_minute_feed_never_authorizes_direction_or_bypasses_15m(self):
        result, _, _ = self._run(one_minute_ready=False)
        self.assertEqual(result["registered_count"], 7)
        self.assertEqual(result["precision_entry"]["status"], "BLOCKED")
        self.assertFalse(result["precision_entry"]["direction_authority"])
        self.assertEqual(result["decision"], "NO_TRADE")
        decision_stage = next(stage for stage in result["stages"] if stage["agent"] == "decision")
        self.assertIn("PRECISION_ENTRY_1M_FEED_NOT_READY", decision_stage["reason_codes"])
        self.assertIn("PRECISION_ENTRY_1M_FEED_NOT_READY", result["paper_execution_gate"]["reason_codes"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])


if __name__ == "__main__":
    import unittest
    unittest.main()
