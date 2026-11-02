import math
import unittest
from core.risk.position_sizing import PositionSizingInput, size_position

class PositionSizingTests(unittest.TestCase):
    def test_size_respects_risk_budget_including_costs(self):
        r = size_position(PositionSizingInput(10000, 100, 98))
        self.assertTrue(r.approved)
        self.assertLessEqual(r.estimated_stop_loss + r.estimated_round_trip_cost, r.risk_budget + 1e-8)
        self.assertLessEqual(r.notional, 10000)
    def test_rejects_zero_stop_distance(self):
        self.assertFalse(size_position(PositionSizingInput(10000, 100, 100)).approved)
    def test_rejects_long_stop_above_entry(self):
        self.assertFalse(size_position(PositionSizingInput(10000, 100, 102)).approved)
    def test_short_stop_must_be_above_entry(self):
        self.assertFalse(size_position(PositionSizingInput(10000, 100, 98, side="SHORT")).approved)
    def test_valid_short_position(self):
        r = size_position(PositionSizingInput(10000, 100, 102, side="SHORT"))
        self.assertTrue(r.approved)
        self.assertLessEqual(r.estimated_stop_loss + r.estimated_round_trip_cost, r.risk_budget + 1e-8)
    def test_rejects_invalid_side(self):
        self.assertFalse(size_position(PositionSizingInput(10000, 100, 98, side="SIDEWAYS")).approved)
    def test_rejects_nonfinite_input(self):
        self.assertFalse(size_position(PositionSizingInput(10000, math.nan, 98)).approved)
    def test_rejects_excess_risk_fraction(self):
        self.assertFalse(size_position(PositionSizingInput(10000, 100, 98, risk_fraction=.02)).approved)
    def test_notional_cap(self):
        r = size_position(PositionSizingInput(10000, 100, 99.99, max_notional_fraction=.5))
        self.assertTrue(r.approved)
        self.assertLessEqual(r.notional, 5000)

    def test_rejects_malformed_numeric_inputs_without_raising(self):
        for field in ("equity", "entry_price", "stop_price", "risk_fraction",
                      "fee_fraction_per_side", "slippage_fraction_per_side",
                      "max_notional_fraction"):
            for invalid in (None, "100", True):
                with self.subTest(field=field, invalid=invalid):
                    values = dict(equity=10000, entry_price=100, stop_price=98)
                    values[field] = invalid
                    result = size_position(PositionSizingInput(**values))
                    self.assertFalse(result.approved)
                    self.assertEqual(result.reason, "invalid_numeric_input")

    def test_rejects_infinite_numeric_inputs(self):
        for field in ("equity", "entry_price", "stop_price", "risk_fraction",
                      "fee_fraction_per_side", "slippage_fraction_per_side",
                      "max_notional_fraction"):
            with self.subTest(field=field):
                values = dict(equity=10000, entry_price=100, stop_price=98)
                values[field] = math.inf
                result = size_position(PositionSizingInput(**values))
                self.assertFalse(result.approved)
                self.assertEqual(result.reason, "non_finite_input")

if __name__ == '__main__': unittest.main()
