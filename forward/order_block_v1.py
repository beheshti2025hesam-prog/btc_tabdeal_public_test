"""Causal order-block context score v1 for canonical native OHLCV.

The score is descriptive context only. No score threshold authorizes a trade;
the strategy quorum and Risk Gate remain the decision authorities.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Sequence

from .native_ohlcv_v1 import NativeCandle

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OrderBlockResultV1:
    version: str
    direction: str
    break_type: str
    zone_low: Decimal
    zone_high: Decimal
    formed_at_ms: int
    break_at_ms: int
    bos_choch_confirmed: bool
    liquidity_sweep: bool
    fair_value_gap: bool
    fresh: bool
    mitigated: bool
    htf_aligned: bool
    volume_expansion: bool
    price_confluence: bool
    score: int
    max_score: int
    source_response_sha256: str
    status: str = "CONTEXT_ONLY"
    score_threshold_authorized: bool = False


def detect_order_block_v1(
    candles: Sequence[NativeCandle],
    *,
    direction: str,
    break_confirmed: bool,
    break_type: str = "BOS",
    htf_direction: str,
    last_swing_high: Decimal | None,
    last_swing_low: Decimal | None,
    ema50: float | None,
    vwap: float | None = None,
    source_response_sha256: str,
) -> OrderBlockResultV1 | None:
    """Find the last opposing candle before a confirmed BOS and score context.

    Bullish block: last bearish candle before a bullish confirmed swing break.
    Bearish block: last bullish candle before a bearish confirmed swing break.
    Search is limited to the supplied closed-candle batch; no future bars or
    trade tape are used. The seven factors are equally weighted descriptive flags.
    """
    candles = tuple(candles)
    if not isinstance(source_response_sha256, str) or not _HASH_RE.fullmatch(source_response_sha256):
        raise ValueError("source_response_sha256 must be a lowercase SHA-256")
    if direction not in ("BULLISH", "BEARISH"):
        return None
    if break_type not in ("BOS", "CHOCH"):
        raise ValueError("break_type must be BOS or CHOCH")
    if not break_confirmed or len(candles) < 4:
        return None
    if any(not isinstance(c.closed, bool) or c.closed is not True for c in candles):
        raise ValueError("order-block input must contain closed candles only")
    if any(candles[i].open_time_ms >= candles[i + 1].open_time_ms for i in range(len(candles) - 1)):
        raise ValueError("order-block candles must be strictly ordered")

    break_index = len(candles) - 1
    block_index = None
    for index in range(break_index - 1, -1, -1):
        candle = candles[index]
        bearish = candle.close < candle.open
        bullish = candle.close > candle.open
        if (direction == "BULLISH" and bearish) or (direction == "BEARISH" and bullish):
            block_index = index
            break
    if block_index is None:
        return None

    block = candles[block_index]
    if direction == "BULLISH":
        zone_low, zone_high = block.low, block.open
    else:
        zone_low, zone_high = block.open, block.high
    if zone_low <= 0 or zone_high < zone_low:
        raise ValueError("invalid order-block zone")

    intervening = candles[block_index + 1:]
    mitigated = any(c.low <= zone_high and c.high >= zone_low for c in intervening)
    fresh = not mitigated

    liquidity_sweep = False
    if direction == "BULLISH" and last_swing_low is not None:
        liquidity_sweep = any(c.low < last_swing_low and c.close > last_swing_low for c in candles[:break_index])
    elif direction == "BEARISH" and last_swing_high is not None:
        liquidity_sweep = any(c.high > last_swing_high and c.close < last_swing_high for c in candles[:break_index])

    fair_value_gap = False
    for middle in range(block_index + 1, break_index):
        left, right = candles[middle - 1], candles[middle + 1]
        if direction == "BULLISH" and right.low > left.high:
            fair_value_gap = True
            break
        if direction == "BEARISH" and right.high < left.low:
            fair_value_gap = True
            break

    htf_aligned = htf_direction == direction
    prior_volumes = [float(c.volume) for c in candles[max(0, break_index - 20):break_index]]
    break_volume = float(candles[break_index].volume)
    volume_expansion = bool(prior_volumes and break_volume > sum(prior_volumes) / len(prior_volumes))
    confluence_levels = []
    if ema50 is not None:
        confluence_levels.append(Decimal(str(ema50)))
    if vwap is not None:
        confluence_levels.append(Decimal(str(vwap)))
    if direction == "BULLISH" and last_swing_high is not None:
        confluence_levels.append(last_swing_high)
    if direction == "BEARISH" and last_swing_low is not None:
        confluence_levels.append(last_swing_low)
    price_confluence = any(zone_low <= level <= zone_high for level in confluence_levels)

    factors = (
        True, liquidity_sweep, fair_value_gap, fresh, htf_aligned,
        volume_expansion, price_confluence,
    )
    return OrderBlockResultV1(
        version="hes-order-block-context-v1",
        direction=direction,
        break_type=break_type,
        zone_low=zone_low,
        zone_high=zone_high,
        formed_at_ms=block.open_time_ms,
        break_at_ms=candles[break_index].close_time_ms,
        bos_choch_confirmed=True,
        liquidity_sweep=liquidity_sweep,
        fair_value_gap=fair_value_gap,
        fresh=fresh,
        mitigated=mitigated,
        htf_aligned=htf_aligned,
        volume_expansion=volume_expansion,
        price_confluence=price_confluence,
        score=sum(factors),
        max_score=len(factors),
        source_response_sha256=source_response_sha256,
    )
