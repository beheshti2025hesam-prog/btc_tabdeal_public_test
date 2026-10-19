"""Deterministic execution-cost model for simulation/paper evaluation.

This module is deliberately execution-free. It models only costs that can be
represented from supplied parameters: fees, spread, and slippage.

Latency and funding are intentionally NOT invented here. They require
timestamped market/funding evidence (or explicit realized execution prices)
and belong in a later data-backed simulation layer.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ExecutionCostConfig:
    """Explicit, deterministic cost assumptions for historical simulation."""

    fee_bps_per_side: float = 0.0
    spread_bps: float = 0.0
    slippage_bps_per_side: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.fee_bps_per_side,
            self.spread_bps,
            self.slippage_bps_per_side,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("execution cost parameters must be finite")
        if any(value < 0 for value in values):
            raise ValueError("execution cost parameters must be non-negative")
        if self.spread_bps >= 20000:
            raise ValueError("spread_bps must be below 20000")
        if self.slippage_bps_per_side >= 10000:
            raise ValueError("slippage_bps_per_side must be below 10000")


@dataclass(frozen=True)
class ExecutionTradeResult:
    """Gross and cost-adjusted result for one completed directional trade."""

    gross_return: float
    net_return: float
    entry_execution_price: float
    exit_execution_price: float
    cost_fraction: float


class ExecutionCostModel:
    """Apply explicit fee/spread/slippage assumptions without execution."""

    def __init__(self, config: ExecutionCostConfig | None = None) -> None:
        self.config = config or ExecutionCostConfig()

    def apply(
        self,
        *,
        direction: int,
        entry_mid_price: float,
        exit_mid_price: float,
    ) -> ExecutionTradeResult:
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or 1")
        prices = (entry_mid_price, exit_mid_price)
        if not all(math.isfinite(value) and value > 0 for value in prices):
            raise ValueError("prices must be finite and positive")

        half_spread = self.config.spread_bps / 20000.0
        slippage = self.config.slippage_bps_per_side / 10000.0

        # Long: buy above mid and sell below mid.
        # Short: sell below mid and buy above mid.
        adverse_entry = half_spread + slippage
        adverse_exit = half_spread + slippage

        if direction == 1:
            entry_exec = entry_mid_price * (1.0 + adverse_entry)
            exit_exec = exit_mid_price * (1.0 - adverse_exit)
        else:
            entry_exec = entry_mid_price * (1.0 - adverse_entry)
            exit_exec = exit_mid_price * (1.0 + adverse_exit)

        gross = direction * (exit_mid_price - entry_mid_price) / entry_mid_price

        fee_rate = self.config.fee_bps_per_side / 10000.0
        entry_fee = entry_exec * fee_rate
        exit_fee = exit_exec * fee_rate
        gross_execution = direction * (exit_exec - entry_exec) / entry_exec
        fee_fraction = (entry_fee + exit_fee) / entry_exec
        net = gross_execution - fee_fraction

        return ExecutionTradeResult(
            gross_return=gross,
            net_return=net,
            entry_execution_price=entry_exec,
            exit_execution_price=exit_exec,
            cost_fraction=fee_fraction + (gross - gross_execution),
        )
