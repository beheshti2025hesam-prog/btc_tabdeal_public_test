from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import pytest

from forward.native_binance_ohlcv_v1 import (
    KlineDataError, fetch_klines, parse_klines,
)

AS_OF = 1_800_000_000_000
RETRIEVED = datetime(2026, 10, 19, tzinfo=timezone.utc)


def row(open_ms, *, close=None, o="100.10", h="102.00", low="99.00",
        c="101.50", volume="12.3400", count=8):
    return [
        open_ms, o, h, low, c, volume,
        open_ms + 899_999 if close is None else close,
        "1234.5000", count, "4.2000", "420.00", "0",
    ]


def parse(rows, *, as_of=AS_OF, market="spot", interval="15m", raw=None):
    payload = raw if raw is not None else json.dumps(rows, separators=(",", ":")).encode()
    return parse_klines(
        rows, market=market, symbol="BTCUSDT", interval=interval,
        as_of_ms=as_of, retrieved_at=RETRIEVED, raw_payload=payload,
    )


def test_parses_native_ohlcv_without_float_coercion_and_records_payload_hash():
    r = row(AS_OF - 1_800_000)
    raw = json.dumps([r], separators=(",", ":")).encode()
    batch = parse([r], raw=raw)
    assert len(batch.candles) == 1
    candle = batch.candles[0]
    assert candle.open == Decimal("100.10")
    assert candle.volume == Decimal("12.3400")
    assert candle.trade_count == 8
    assert batch.payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert batch.market == "spot"


def test_supports_usdm_market_without_changing_row_semantics():
    batch = parse([row(AS_OF - 900_000)], market="usdm_futures")
    assert batch.candles[0].market == "usdm_futures"


def test_discards_current_not_yet_closed_candle():
    closed = row(AS_OF - 1_800_000)
    open_bar = row(AS_OF)
    batch = parse([closed, open_bar])
    assert [c.open_time_ms for c in batch.candles] == [closed[0]]
    assert batch.discarded_open_candles == 1


def test_reports_gaps_instead_of_fabricating_candles():
    a, b = row(AS_OF - 2_700_000), row(AS_OF - 900_000)
    batch = parse([a, b])
    assert len(batch.candles) == 2
    assert len(batch.gaps) == 1
    assert batch.gaps[0].expected_open_time_ms == a[0] + 900_000
    assert batch.gaps[0].observed_open_time_ms == b[0]


@pytest.mark.parametrize("bad", [
    "not-a-list",
    [[1, "1", "2", "1", "2", "3", 899999, "4", 1, "1", "1", "0"]],
    [[900_000, "1", "2", "1", "2", "-1", 1_799_999, "4", 1, "1", "1", "0"]],
    [[900_000, "1", "0.5", "1", "2", "3", 1_799_999, "4", 1, "1", "1", "0"]],
])
def test_rejects_bad_response_shapes_ranges_and_values(bad):
    with pytest.raises(KlineDataError):
        parse(bad)


def test_rejects_duplicate_candle_open_time():
    r = row(AS_OF - 900_000)
    with pytest.raises(KlineDataError, match="duplicate"):
        parse([r, r])


def test_rejects_unsorted_rows_instead_of_silently_reordering():
    a, b = row(AS_OF - 1_800_000), row(AS_OF - 900_000)
    with pytest.raises(KlineDataError, match="increasing"):
        parse([b, a])


def test_rejects_bad_scope_and_naive_times():
    with pytest.raises(KlineDataError, match="unsupported market"):
        parse([row(AS_OF - 900_000)], market="tabdeal")
    with pytest.raises(KlineDataError, match="timezone-aware"):
        parse_klines([row(AS_OF - 900_000)], market="spot", symbol="BTCUSDT",
                     interval="15m", as_of_ms=AS_OF,
                     retrieved_at=datetime(2026, 10, 19), raw_payload=b"[]")


def test_fetch_is_explicit_and_rejects_invalid_limits_before_network():
    with pytest.raises(KlineDataError, match="limit"):
        fetch_klines(market="spot", limit=0)
    with pytest.raises(KlineDataError, match="unsupported market"):
        fetch_klines(market="tabdeal")
