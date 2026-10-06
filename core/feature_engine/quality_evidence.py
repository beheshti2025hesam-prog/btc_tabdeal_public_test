"""Causal market-structure evidence for POST-QUALITY-BASELINE.

This module is descriptive only. It derives evidence from completed candles and
never invents missing evidence. All state used for a candle comes from candles
that were already closed at that candle's timestamp.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class QualityEvidence:
    htf_trend: str | None
    htf_alignment: bool | None
    structure_bias: str | None
    structure_break_confirmed: bool | None
    liquidity_event_confirmed: bool | None
    fvg_present: bool | None
    order_block_present: bool | None
    location_valid: bool | None
    entry_trigger_confirmed: bool | None
    displacement_confirmed: bool | None
    momentum_confirmed: bool | None
    participation_confirmed: bool | None
    contradiction: bool | None
    stop_valid: bool | None
    stop_price: float | None
    target_price: float | None
    rr: float | None


class QualityEvidenceEngine:
    """Build causal evidence snapshots from OHLCV candles.

    Defaults are deliberately conservative: insufficient history returns None,
    never a guessed True/False.
    """

    def __init__(self, swing_left: int = 2, swing_right: int = 2,
                 atr_period: int = 14, ema_fast: int = 50, ema_slow: int = 200):
        if min(swing_left, swing_right, atr_period, ema_fast, ema_slow) <= 0:
            raise ValueError("periods must be positive")
        self.left = swing_left
        self.right = swing_right
        self.atr_period = atr_period
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    @staticmethod
    def _ema(values, period):
        if len(values) < period:
            return None
        value = sum(values[:period]) / period
        alpha = 2.0 / (period + 1.0)
        for item in values[period:]:
            value = alpha * item + (1.0 - alpha) * value
        return value

    @staticmethod
    def _atr(candles, period):
        if len(candles) < period + 1:
            return None
        trs = []
        for i in range(1, len(candles)):
            c, p = candles[i], candles[i - 1]
            trs.append(max(c.high - c.low, abs(c.high - p.close),
                           abs(c.low - p.close)))
        return sum(trs[-period:]) / period if len(trs) >= period else None

    def _pivots(self, candles):
        highs, lows = [], []
        for i in range(self.left, len(candles) - self.right):
            c = candles[i]
            ns = candles[i-self.left:i] + candles[i+1:i+self.right+1]
            if c.high >= max(x.high for x in ns):
                highs.append((i, c.high))
            if c.low <= min(x.low for x in ns):
                lows.append((i, c.low))
        return highs, lows

    @staticmethod
    def _resample(candles, factor):
        if factor <= 1:
            return list(candles)
        out = []
        for i in range(0, len(candles), factor):
            group = candles[i:i+factor]
            if len(group) != factor:
                break
            if any(group[j].start != group[j-1].end for j in range(1, len(group))):
                continue
            out.append(type(group[0])(
                group[0].symbol, group[0].timeframe_seconds * factor,
                group[0].start, group[-1].end, group[0].open,
                max(x.high for x in group), min(x.low for x in group),
                group[-1].close, sum(x.volume for x in group),
                sum(x.trade_count for x in group)))
        return out

    def _htf(self, candles):
        if not candles:
            return None, None
        # 15m -> 1h; for other timeframes use a four-bar higher timeframe.
        htf = self._resample(candles, 4)
        closes = [c.close for c in htf]
        fast = self._ema(closes, self.ema_fast)
        slow = self._ema(closes, self.ema_slow)
        if fast is None or slow is None:
            return None, None
        trend = "long" if fast > slow and closes[-1] > fast else "short" if fast < slow and closes[-1] < fast else "range"
        alignment = trend if trend != "range" else None
        return trend, alignment

    def build(self, candles, index):
        if index < 1 or index >= len(candles):
            raise IndexError("index outside candle series")
        current = candles[index]
        history = list(candles[:index + 1])
        if len(history) < max(self.atr_period + 2, self.ema_fast, self.left + self.right + 3):
            return QualityEvidence(None, None, None, None, None, None, None, None,
                                   None, None, None, None, None, None, None, None, None)

        htf_trend, _ = self._htf(history)
        htf_alignment = htf_trend in ("long", "short")
        piv_highs, piv_lows = self._pivots(history[:-self.right] if len(history) > self.right else [])
        last_high = piv_highs[-1] if piv_highs else None
        last_low = piv_lows[-1] if piv_lows else None
        prev_high = piv_highs[-2] if len(piv_highs) > 1 else None
        prev_low = piv_lows[-2] if len(piv_lows) > 1 else None

        structure_bias = None
        if last_high and last_low:
            if prev_high and prev_low:
                if last_high[1] > prev_high[1] and last_low[1] > prev_low[1]:
                    structure_bias = "long"
                elif last_high[1] < prev_high[1] and last_low[1] < prev_low[1]:
                    structure_bias = "short"
            if structure_bias is None:
                if current.close > last_high[1]:
                    structure_bias = "long"
                elif current.close < last_low[1]:
                    structure_bias = "short"

        bos_long = bool(last_high and current.close > last_high[1])
        bos_short = bool(last_low and current.close < last_low[1])
        structure_break = bos_long or bos_short

        sweep_long = bool(last_low and current.low < last_low[1] and current.close > last_low[1])
        sweep_short = bool(last_high and current.high > last_high[1] and current.close < last_high[1])
        liquidity = sweep_long or sweep_short

        fvg_long = len(history) >= 3 and current.low > history[-3].high
        fvg_short = len(history) >= 3 and current.high < history[-3].low
        fvg_present = fvg_long or fvg_short

        ob_present = False
        if len(history) >= 4:
            before = history[-2]
            displacement = history[-1]
            ob_present = (
                (displacement.close > displacement.open and before.close < before.open)
                or (displacement.close < displacement.open and before.close > before.open)
            )

        atr = self._atr(history, self.atr_period)
        body = abs(current.close - current.open)
        rng = current.high - current.low
        ratios = []
        for c in history[-min(20, len(history)):]:
            r = c.high - c.low
            if r > 0:
                ratios.append(abs(c.close - c.open) / r)
        median = sorted(ratios)[len(ratios)//2] if ratios else None
        displacement = bool(rng > 0 and median is not None and body / rng >= median and body / rng >= 0.5)

        recent_touch = False
        if atr is not None and atr > 0:
            ema20 = self._ema([c.close for c in history], min(20, len(history)))
            if ema20 is not None:
                recent_touch = abs(current.close - ema20) <= atr
        location = recent_touch or fvg_present or ob_present

        entry = bool(
            (sweep_long and current.close > current.open)
            or (sweep_short and current.close < current.open)
            or (bos_long and current.close > current.open and displacement)
            or (bos_short and current.close < current.open and displacement)
        )

        momentum = bool(
            len(history) >= 4 and
            ((current.close > history[-4].close and current.close > current.open)
             or (current.close < history[-4].close and current.close < current.open))
        )
        avg_volume = sum(c.volume for c in history[-20:]) / min(20, len(history))
        participation = bool(avg_volume > 0 and current.volume >= avg_volume)

        contradiction = None
        if htf_trend in ("long", "short") and structure_bias in ("long", "short"):
            contradiction = htf_trend != structure_bias
        if htf_trend == "long" and bos_short:
            contradiction = True
        if htf_trend == "short" and bos_long:
            contradiction = True

        stop_price = None
        target_price = None
        rr = None
        if atr is not None and atr > 0:
            if sweep_long and last_low:
                stop_price = last_low[1] - 0.25 * atr
                target_price = current.close + 3.0 * (current.close - stop_price)
            elif sweep_short and last_high:
                stop_price = last_high[1] + 0.25 * atr
                target_price = current.close - 3.0 * (stop_price - current.close)
            elif bos_long:
                stop_price = current.close - atr
                target_price = current.close + 3.0 * atr
            elif bos_short:
                stop_price = current.close + atr
                target_price = current.close - 3.0 * atr
            if stop_price is not None and target_price is not None:
                risk = abs(current.close - stop_price)
                reward = abs(target_price - current.close)
                if risk > 0:
                    rr = reward / risk
        stop_valid = stop_price is not None and (
            (bos_long or sweep_long) and stop_price < current.close
            or (bos_short or sweep_short) and stop_price > current.close
        )

        direction = "long" if (sweep_long or bos_long) and not bos_short else "short" if (sweep_short or bos_short) and not bos_long else None
        if direction is not None and htf_trend in ("long", "short") and htf_trend != direction:
            contradiction = True

        return QualityEvidence(
            htf_trend=htf_trend,
            htf_alignment=htf_alignment,
            structure_bias=structure_bias,
            structure_break_confirmed=structure_break,
            liquidity_event_confirmed=liquidity,
            fvg_present=fvg_present,
            order_block_present=ob_present,
            location_valid=location,
            entry_trigger_confirmed=entry,
            displacement_confirmed=displacement,
            momentum_confirmed=momentum,
            participation_confirmed=participation,
            contradiction=contradiction,
            stop_valid=stop_valid,
            stop_price=stop_price,
            target_price=target_price,
            rr=rr,
        )
