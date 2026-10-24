import json, tempfile, unittest
from pathlib import Path
from scripts.run_gateio_analysis_v1 import run

class GateIOAnalysisIntegrationTests(unittest.TestCase):
 def test_real_input_path_fails_closed(self):
  # Integration test against current validated live candle files on the VPS.
  result=run(Path("/opt/hes-trade-agent"))
  self.assertEqual(result["source"],"gateio_public_spot")
  self.assertEqual(result["decision"]["decision"],"NO_TRADE")
  self.assertFalse(result["execution_enabled"])
  self.assertFalse(result["orders_placed"])
  self.assertEqual(set(result["market_features"]),{"15m","1h","4h"})
 def test_decision_output_has_explicit_gates(self):
  result=run(Path("/opt/hes-trade-agent"))
  self.assertEqual(result["decision"]["signal_state"],"NO_CANDIDATE")
  self.assertEqual(result["decision"]["confirmation_state"],"NOT_CONFIGURED")
  self.assertEqual(result["decision"]["risk_state"],"RISK_NOT_APPROVED")
  self.assertTrue(result["decision"]["no_trade_reason"])
if __name__=="__main__": unittest.main()
