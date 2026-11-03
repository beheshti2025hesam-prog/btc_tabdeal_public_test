from __future__ import annotations

import unittest

from forward.precision_entry_engine_v1 import evaluate_precision_entry


def candles(n: int = 60, start: int = 1_800_000_000):
    rows = []
    for i in range(n):
        open_price = 100 + i * 0.01
        close_price = open_price + 0.005
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": "1m",
            "open_time": start + i * 60,
            "close_time": start + (i + 1) * 60,
            "open": str(open_price),
            "high": str(close_price + 0.02),
            "low": str(open_price - 0.02),
            "close": str(close_price),
            "volume": "10",
            "quote_volume": "1000",
            "closed": True,
        })
    return rows


def context(**changes):
    value = {
        "schema": "hes_strategy_entry_context_v1",
        "source": "strategy_policy_v2",
        "symbol": "BTC_USDT",
        "timeframe": "15m",
        "direction": "LONG",
        "setup_id": "BTC_USDT:15m:1800000000:LONG",
        "evidence_sha256": "a" * 64,
        "valid_until": 1_800_004_500,
        "planned_entry_price": 100.70,
        "entry_zone_low": 100.40,
        "entry_zone_high": 100.70,
        "entry_zone_policy": "FAVORABLE_SIDE_RISK_FRACTION_V1",
        "entry_zone_fraction_of_risk": 0.25,
        "stop_price": 99.50,
        "target_price": 104.60,
    }
    value.update(changes)
    return value


def run(rows=None, *, direction="LONG", setup=True, risk="RISK_APPROVED",
        ctx=None, now=None, min_rr=3.0):
    values = rows or candles()
    return evaluate_precision_entry(
        setup_direction=direction,
        candles_1m=values,
        setup_validated_15m=setup,
        risk_gate_state=risk,
        now_s=now if now is not None else values[-1]["close_time"],
        setup_context=context() if ctx is None else ctx,
        min_rr=min_rr,
    )


class PrecisionEntryTests(unittest.TestCase):
    def test_blocked_without_15m_setup(self):
        result = run(setup=False)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("15M_SETUP_NOT_VALIDATED", result["reason_codes"])

    def test_blocked_when_risk_gate_not_approved(self):
        result = run(risk="RISK_REJECTED")
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("RISK_GATE_NOT_APPROVED", result["reason_codes"])

    def test_blocked_without_provenance_bound_setup_context(self):
        result = evaluate_precision_entry(
            setup_direction="LONG", candles_1m=candles(), setup_validated_15m=True,
            risk_gate_state="RISK_APPROVED", now_s=candles()[-1]["close_time"],
            setup_context=None,
        )
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("ENTRY_CONTEXT_MISSING", result["reason_codes"])

    def test_blocked_on_wrong_context_scope_or_direction(self):
        for changes, expected in (
            ({"symbol": "ETH_USDT"}, "ENTRY_CONTEXT_SCOPE_INVALID"),
            ({"direction": "SHORT"}, "ENTRY_CONTEXT_DIRECTION_MISMATCH"),
            ({"timeframe": "1m"}, "ENTRY_CONTEXT_SCOPE_INVALID"),
            ({"schema": "unknown"}, "ENTRY_CONTEXT_SCHEMA_INVALID"),
        ):
            with self.subTest(changes=changes):
                result = run(ctx=context(**changes))
                self.assertEqual(result["state"], "BLOCKED")
                self.assertIn(expected, result["reason_codes"])

    def test_blocked_when_context_expired_or_provenance_missing(self):
        for changes, expected in (
            ({"valid_until": 1_800_000_000}, "ENTRY_CONTEXT_EXPIRED"),
            ({"evidence_sha256": "not-a-digest"}, "ENTRY_CONTEXT_PROVENANCE_INVALID"),
            ({"setup_id": ""}, "ENTRY_CONTEXT_ID_INVALID"),
        ):
            with self.subTest(changes=changes):
                result = run(ctx=context(**changes))
                self.assertEqual(result["state"], "BLOCKED")
                self.assertIn(expected, result["reason_codes"])

    def test_blocked_on_wrong_stop_target_direction(self):
        result = run(ctx=context(stop_price=101.0))
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("STOP_TARGET_DIRECTION_INVALID", result["reason_codes"])

    def test_blocked_when_worst_case_zone_rr_is_below_three(self):
        result = run(ctx=context(target_price=104.0))
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("RISK_REWARD_BELOW_MINIMUM", result["reason_codes"])

    def test_minimum_rr_cannot_be_lowered_below_three(self):
        result = run(min_rr=2.5)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("MINIMUM_RR_POLICY_INVALID", result["reason_codes"])

    def test_blocked_on_source_identity_mismatch(self):
        rows = candles()
        rows[-1]["source"] = "other_venue"
        result = run(rows)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("SOURCE_IDENTITY_MISMATCH", result["reason_codes"])

    def test_blocked_on_gap(self):
        rows = candles()
        rows[-1]["open_time"] += 60
        rows[-1]["close_time"] += 60
        result = run(rows)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("CANDLE_INTERVAL_GAP", result["reason_codes"])

    def test_blocked_on_stale_candles(self):
        rows = candles()
        result = run(rows, now=rows[-1]["close_time"] + 121)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertIn("CANDLE_FEED_STALE", result["reason_codes"])

    def test_wait_when_micro_trigger_is_missing(self):
        rows = candles()
        rows[-1].update({
            "open": "100.59", "high": "100.61", "low": "100.57",
            "close": "100.595", "volume": "10", "quote_volume": "1000",
        })
        result = run(rows, ctx=context())
        self.assertEqual(result["state"], "WAIT")
        self.assertIn("MICROSTRUCTURE_TRIGGER_NOT_CONFIRMED", result["reason_codes"])

    def test_ready_requires_15m_confirmation_risk_and_provenance_context(self):
        rows = candles()
        rows[-1].update({
            "open": "100.58", "high": "100.66", "low": "100.56",
            "close": "100.65", "volume": "20", "quote_volume": "2000",
        })
        result = run(rows, ctx=context())
        self.assertEqual(result["state"], "READY", result["reason_codes"])
        self.assertGreaterEqual(result["evidence"]["planned_rr_worst_case"], 3.0)
        self.assertTrue(result["evidence"]["vwap_ema_alignment"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])


    def test_short_ready_requires_the_same_provenance_and_three_risk_reward_gates(self):
        rows = []
        start = 1_800_000_000
        for i in range(60):
            open_price = 100 - i * 0.01
            close_price = open_price - 0.005
            rows.append({
                "schema": "hes_global_candle_v1", "source": "gateio_public_spot",
                "symbol": "BTC_USDT", "timeframe": "1m",
                "open_time": start + i * 60, "close_time": start + (i + 1) * 60,
                "open": str(open_price), "high": str(open_price + 0.02),
                "low": str(close_price - 0.02), "close": str(close_price),
                "volume": "10", "quote_volume": "1000", "closed": True,
            })
        rows[-1].update({
            "open": "99.42", "high": "99.44", "low": "99.30",
            "close": "99.35", "volume": "20", "quote_volume": "2000",
        })
        short_context = context(
            direction="SHORT", planned_entry_price=99.30,
            entry_zone_low=99.30, entry_zone_high=99.60,
            entry_zone_policy="FAVORABLE_SIDE_RISK_FRACTION_V1",
            entry_zone_fraction_of_risk=0.25,
            stop_price=100.50, target_price=95.40,
        )
        result = evaluate_precision_entry(
            setup_direction="SHORT", candles_1m=rows, setup_validated_15m=True,
            risk_gate_state="RISK_APPROVED", now_s=rows[-1]["close_time"],
            setup_context=short_context,
        )
        self.assertEqual(result["state"], "READY", result["reason_codes"])
        self.assertGreaterEqual(result["evidence"]["planned_rr_worst_case"], 3.0)
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])

    def test_authority_never_enables_execution(self):
        result = run()
        self.assertEqual(result["authority"], "ADVISORY_ONLY_RISK_GATE_UNCHANGED")
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["orders_placed"])


if __name__ == "__main__":
    unittest.main()


    def test_blocked_on_missing_or_changed_entry_zone_policy(self):
        for changes in (
            {"entry_zone_policy": "UNKNOWN"},
            {"entry_zone_fraction_of_risk": 0.5},
            {"entry_zone_high": 100.8},
        ):
            with self.subTest(changes=changes):
                result = run(ctx=context(**changes))
                self.assertEqual(result["state"], "BLOCKED")
                self.assertIn("ENTRY_CONTEXT_ZONE_POLICY_INVALID", result["reason_codes"])
