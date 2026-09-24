"""Mother Agent - deterministic candle-path backtest engine v1.1.

Research/evaluation only. No live execution and no exchange connectivity.
"""
from dataclasses import dataclass
from datetime import datetime
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
    symbol: str | None = None
    quantity: float = 1.0


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
    symbol: str | None = None
    quantity: float = 1.0


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[SimulatedTrade, ...]
    metrics: EvaluationMetrics
    equity_curve: tuple[float, ...]


class BacktestEngine:
    """Simulate fixed-quantity signal intents against historical candles.

    Signals may optionally identify a symbol. Symbol-scoped signals are matched
    only to candles for that symbol, preventing cross-market contamination.
    A signal with no symbol keeps v1 compatibility and uses the full candle set.

    Each signal represents one position. Overlapping positions are skipped:
    this keeps the v1 execution model deterministic and prevents multiple
    signals from reusing the same open position.

    Entry occurs at the first matching candle whose end is after the signal
    timestamp. Stop/target checks use candle OHLC. If both are touched in one
    candle, stop wins conservatively because intrabar ordering is unknowable
    from OHLC.
    """

    def __init__(
        self,
        *,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
    ):
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("fee_bps and slippage_bps must be nonnegative")
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def run(
        self,
        candles: Sequence[Candle],
        signals: Iterable[BacktestSignal],
        *,
        starting_capital: float = 1.0,
    ) -> BacktestResult:
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        ordered = sorted(candles, key=lambda c: (c.symbol, c.start))
        signal_list = sorted(signals, key=lambda s: s.timestamp)
        self._validate_timestamps(ordered, signal_list)
        trades: list[SimulatedTrade] = []
        last_exit_by_symbol: dict[str, object] = {}

        for signal in signal_list:
            if (
                signal.entry_price <= 0
                or signal.stop_price <= 0
                or signal.target_price <= 0
                or signal.quantity <= 0
            ):
                continue

            matching = [
                candle
                for candle in ordered
                if (signal.symbol is None or candle.symbol == signal.symbol)
                and candle.end > signal.timestamp
            ]
            if not matching:
                continue

            entry_candle = matching[0]
            position_key = signal.symbol or entry_candle.symbol
            previous_exit = last_exit_by_symbol.get(position_key)
            if previous_exit is not None and signal.timestamp < previous_exit:
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
            for candle in matching:
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
            gross_per_unit = (
                executed_exit - entry
                if signal.side == BacktestSide.LONG
                else entry - executed_exit
            )
            gross = gross_per_unit * signal.quantity
            notional = (abs(entry) + abs(executed_exit)) * signal.quantity
            fees = notional * (self.fee_bps / 10000.0)
            net = gross - fees
            trades.append(
                SimulatedTrade(
                    entry_time=entry_candle.start,
                    exit_time=exit_time,
                    side=signal.side,
                    entry_price=entry,
                    exit_price=executed_exit,
                    gross_pnl=gross,
                    fees=fees,
                    net_pnl=net,
                    exit_reason=exit_reason,
                    symbol=entry_candle.symbol,
                    quantity=signal.quantity,
                )
            )
            last_exit_by_symbol[position_key] = exit_time

        pnls = [trade.net_pnl for trade in trades]
        metrics = EvaluationMetricsCalculator().calculate(
            pnls, starting_capital=starting_capital
        )
        equity = []
        running = starting_capital
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

    @staticmethod
    def _validate_timestamps(candles: Sequence[Candle], signals: Sequence[BacktestSignal]) -> None:
        """Reject naive datetimes so historical ordering cannot depend on local time."""
        for candle in candles:
            if not isinstance(candle.start, datetime) or candle.start.tzinfo is None:
                raise ValueError("candle start timestamp must be timezone-aware")
            if not isinstance(candle.end, datetime) or candle.end.tzinfo is None:
                raise ValueError("candle end timestamp must be timezone-aware")
        for signal in signals:
            if not isinstance(signal.timestamp, datetime) or signal.timestamp.tzinfo is None:
                raise ValueError("signal timestamp must be timezone-aware")
