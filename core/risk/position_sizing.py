"""Pure, execution-free position sizing from stop distance and risk budget.

This module computes a proposal only. It never places orders or changes capital.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PositionSizingInput:
    equity: float
    entry_price: float
    stop_price: float
    side: str = "LONG"
    risk_fraction: float = 0.005
    fee_fraction_per_side: float = 0.001
    slippage_fraction_per_side: float = 0.0005
    max_notional_fraction: float = 1.0


@dataclass(frozen=True)
class PositionSizingResult:
    approved: bool
    quantity: float
    notional: float
    risk_budget: float
    estimated_stop_loss: float
    estimated_round_trip_cost: float
    reason: str


def size_position(data: PositionSizingInput) -> PositionSizingResult:
    vals = (
        data.equity,
        data.entry_price,
        data.stop_price,
        data.risk_fraction,
        data.fee_fraction_per_side,
        data.slippage_fraction_per_side,
        data.max_notional_fraction,
    )
    # Dataclass annotations do not enforce runtime types. Reject malformed input
    # before math.isfinite/arithmetic so invalid external payloads fail closed.
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vals):
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "invalid_numeric_input")
    if not all(math.isfinite(value) for value in vals):
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "non_finite_input")
    if data.equity <= 0 or data.entry_price <= 0 or data.stop_price <= 0:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "non_positive_equity_or_price")
    if data.entry_price == data.stop_price:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "zero_stop_distance")
    if data.side not in ("LONG", "SHORT"):
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "invalid_side")
    if data.side == "LONG" and data.stop_price >= data.entry_price:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "long_stop_must_be_below_entry")
    if data.side == "SHORT" and data.stop_price <= data.entry_price:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "short_stop_must_be_above_entry")
    if not 0 < data.risk_fraction <= 0.01:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "risk_fraction_out_of_bounds")
    if not 0 <= data.fee_fraction_per_side <= 0.02 or not 0 <= data.slippage_fraction_per_side <= 0.02:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "cost_out_of_bounds")
    if not 0 < data.max_notional_fraction <= 1:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "notional_cap_out_of_bounds")
    stop_fraction = abs(data.entry_price - data.stop_price) / data.entry_price
    cost_fraction = 2 * (data.fee_fraction_per_side + data.slippage_fraction_per_side)
    loss_fraction = stop_fraction + cost_fraction
    if not math.isfinite(loss_fraction) or loss_fraction <= 0:
        return PositionSizingResult(False, 0, 0, 0, 0, 0, "invalid_loss_fraction")
    budget = data.equity * data.risk_fraction
    raw_notional = budget / loss_fraction
    notional = min(raw_notional, data.equity * data.max_notional_fraction)
    qty = notional / data.entry_price
    stop_loss = notional * stop_fraction
    costs = notional * cost_fraction
    if not all(math.isfinite(v) and v >= 0 for v in (notional, qty, stop_loss, costs)) or qty <= 0:
        return PositionSizingResult(False, 0, 0, budget, 0, 0, "invalid_computed_size")
    return PositionSizingResult(True, qty, notional, budget, stop_loss, costs, "ok")
