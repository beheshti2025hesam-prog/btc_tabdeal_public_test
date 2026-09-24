"""Mother Agent - deterministic candle-path backtest engine v1.0.

Research/evaluation only. No live execution and no exchange connectivity.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

from core.data_engine.candles import Candle
from core.evaluation.metrics import EvaluationMetrics, EvaluationMetricsCalculator


class BacktestSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class BacktestSignal:
    timestamp: object
    side: BacktestSide
    entry_price: float
    stop_price: float
    target_price: float


@dataclass(frozen=True)
class SimulatedTrade:
    entry_time: object
    exit_time: object
    side: BacktestSide
    entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    net_pnl: float
    exit_reason: str


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[SimulatedTrade, ...]
    metrics: EvaluationMetrics
    equity_curve: tuple[float, ...]


class BacktestEngine:
    """Simulate fixed-risk signal intents against historical candles.

    Entry occurs at the first candle whose end is after the signal timestamp.
    Stop/target checks use candle OHLC. If both are touched in one candle,
    stop wins conservatively because intrabar ordering is unknowable from OHLC.
    """

    def __init__(self, *, fee_bps: float = 0.0, slippage_bps: float = 0.0):
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("fee_bps and slippage_bps must be nonnegative")
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def run(
        self,
        candles: Sequence[Candle],
        signals: Iterable[BacktestSignal],
    ) -> BacktestResult:
        ordered = sorted(candles, key=lambda c: (c.symbol, c.start))
        signal_list = sorted(signals, key=lambda s: s.timestamp)
        trades: list[SimulatedTrade] = []

        for signal in signal_list:
            if signal.entry_price <= 0 or signal.stop_price <= 0 or signal.target_price <= 0:
                continue
            entry_index = next(
                (i for i, candle in enumerate(ordered) if candle.end > signal.timestamp),
                None,
            )
            if entry_index is None:
                continue

            entry = self._apply_entry_slippage(signal.entry_price, signal.side)
            if signal.side == BacktestSide.LONG:
                if signal.stop_price >= entry or signal.target_price <= entry:
                    continue
            else:
                if signal.stop_price <= entry or signal.target_price >= entry:
                    continue

            exit_price = None
            exit_reason = None
            exit_time = None
            for candle in ordered[entry_index:]:
                if signal.side == BacktestSide.LONG:
                    stop_hit = candle.low <= signal.stop_price
                    target_hit = candle.high >= signal.target_price
                else:
                    stop_hit = candle.high >= signal.stop_price
                    target_hit = candle.low <= signal.target_price

                if stop_hit:
                    exit_price, exit_reason = signal.stop_price, "STOP"
                elif target_hit:
                    exit_price, exit_reason = signal.target_price, "TARGET"
                else:
                    continue
                exit_time = candle.end
                break

            if exit_price is None:
                continue

            executed_exit = self._apply_exit_slippage(exit_price, signal.side)
            gross = (
                executed_exit - entry
                if signal.side == BacktestSide.LONG
                else entry - executed_exit
            )
            notional = abs(entry) + abs(executed_exit)
            fees = notional * (self.fee_bps / 10000.0)
            net = gross - fees
            trades.append(
                SimulatedTrade(
                    entry_time=ordered[entry_index].start,
                    exit_time=exit_time,
                    side=signal.side,
                    entry_price=entry,
                    exit_price=executed_exit,
                    gross_pnl=gross,
                    fees=fees,
                    net_pnl=net,
                    exit_reason=exit_reason,
                )
            )

        pnls = [trade.net_pnl for trade in trades]
        metrics = EvaluationMetricsCalculator().calculate(pnls)
        equity = []
        running = 0.0
        for pnl in pnls:
            running += pnl
            equity.append(running)
        return BacktestResult(tuple(trades), metrics, tuple(equity))

    def _apply_entry_slippage(self, price: float, side: BacktestSide) -> float:
        move = price * self.slippage_bps / 10000.0
        return price + move if side == BacktestSide.LONG else price - move

    def _apply_exit_slippage(self, price: float, side: BacktestSide) -> float:
        move = price * self.slippage_bps / 10000.0
        return price - move if side == BacktestSide.LONG else price + move
