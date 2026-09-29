"""Frozen OOS protocol for repeatable real-data backtest evidence.

This protocol is evidence configuration, not a strategy parameter set.
It must not be tuned to improve results on the observed dataset.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OOSProtocol:
    protocol_id: str
    train_size: int
    test_size: int
    step_size: int
    embargo_size: int
    expected_fold_count: int


# One observation of embargo is required because a decision's realized
# next-candle outcome becomes available one observation later.
REAL_BTC_USDT_OOS_V1 = OOSProtocol(
    protocol_id="oos-real-btcusdt-v2-800x400x400-e1",
    train_size=800,
    test_size=400,
    step_size=400,
    embargo_size=1,
    expected_fold_count=8,
)
