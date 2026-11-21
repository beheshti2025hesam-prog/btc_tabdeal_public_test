"""Regression tests for the frozen real-data OOS evidence protocol."""

import unittest

from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1


class OOSProtocolTests(unittest.TestCase):
    def test_real_btc_usdt_protocol_is_frozen(self):
        protocol = REAL_BTC_USDT_OOS_V1
        self.assertEqual(protocol.protocol_id, "oos-real-btcusdt-v1-800x400x400-e0")
        self.assertEqual(protocol.train_size, 800)
        self.assertEqual(protocol.test_size, 400)
        self.assertEqual(protocol.step_size, 400)
        self.assertEqual(protocol.embargo_size, 0)
        self.assertEqual(protocol.expected_fold_count, 8)

    def test_protocol_produces_eight_folds_for_current_snapshot_observation_count(self):
        protocol = REAL_BTC_USDT_OOS_V1
        observations = 4062
        available = observations - protocol.train_size - protocol.embargo_size
        fold_count = 0
        while available >= protocol.test_size:
            fold_count += 1
            available -= protocol.step_size
        self.assertEqual(fold_count, protocol.expected_fold_count)


if __name__ == "__main__":
    unittest.main()
