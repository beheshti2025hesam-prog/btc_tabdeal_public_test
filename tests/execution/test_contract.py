"""Tests for the execution-free adapter port contract."""

import unittest

from core.execution.contract import (
    ExecutionAction,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
)


class ExecutionContractTests(unittest.TestCase):
    def test_request_defaults_to_disabled_mode(self):
        request = ExecutionRequest(
            request_id="req-1",
            action=ExecutionAction.ENTER_LONG,
            symbol="BTC_USDT",
            price=100.0,
        )
        self.assertEqual(request.mode, ExecutionMode.DISABLED)

    def test_contract_is_venue_agnostic(self):
        request = ExecutionRequest(
            request_id="req-2",
            action=ExecutionAction.CLOSE_LONG,
            symbol="BTC_USDT",
            price=101.0,
            mode=ExecutionMode.SHADOW,
        )
        self.assertEqual(request.symbol, "BTC_USDT")
        self.assertEqual(request.action, ExecutionAction.CLOSE_LONG)

    def test_result_is_explicit(self):
        result = ExecutionResult(
            request_id="req-3",
            accepted=False,
            reason="execution_disabled",
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.reason, "execution_disabled")


if __name__ == "__main__":
    unittest.main()
