import unittest
from scripts.candidate_c_exit_engine import resolve_bar_exit, POLICY_ID

class CandidateCExitEngineTests(unittest.TestCase):
    def test_long_stop_only(self):
        self.assertEqual(resolve_bar_exit("long", {"open": 100, "high": 105, "low": 97}, 98, 104)["exit_reason"], "stop_loss")

    def test_long_target_only(self):
        self.assertEqual(resolve_bar_exit("long", {"open": 100, "high": 105, "low": 99}, 98, 104)["exit_reason"], "take_profit")

    def test_long_same_bar_is_stop_first(self):
        result = resolve_bar_exit("long", {"open": 100, "high": 105, "low": 97}, 98, 104)
        self.assertEqual(result["exit_reason"], "stop_loss")
        self.assertTrue(result["same_bar_ambiguity"])
        self.assertEqual(result["policy_id"], POLICY_ID)

    def test_short_same_bar_is_stop_first(self):
        result = resolve_bar_exit("short", {"open": 100, "high": 105, "low": 95}, 104, 96)
        self.assertEqual(result["exit_reason"], "stop_loss")
        self.assertTrue(result["same_bar_ambiguity"])

    def test_no_touch(self):
        self.assertIsNone(resolve_bar_exit("long", {"open": 100, "high": 103, "low": 99}, 98, 104))

    def test_invalid_side_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve_bar_exit("buy", {"open": 100, "high": 1, "low": 0}, -1, 2)

    def test_invalid_ohlc_fails_closed(self):
        with self.assertRaises(ValueError):
            resolve_bar_exit("long", {"open": 1, "high": 1, "low": 2}, 0, 3)

if __name__ == "__main__":
    unittest.main()
