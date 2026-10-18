from datetime import datetime, timezone
from decimal import Decimal

import pytest

from wallex_native_candles_v1 import WallexCandleError, RESOLUTION_SECONDS, parse_history

UTC = timezone.utc
AS_OF = datetime(2026, 10, 17, 13, 2, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 17, 13, 2, 1, tzinfo=UTC)


def payload(ts=(1792232400, 1792232460), o=("100.00", "101"), h=("102", "103"),
            l=("99", "100"), c=("101", "102.50"), v=("0.123400", "0")):
    return {"s":"ok", "t":list(ts), "o":list(o), "h":list(h), "l":list(l), "c":list(c), "v":list(v)}


def parse(p, as_of=AS_OF):
    return parse_history(p, symbol="BTCUSDT", resolution="1", as_of=as_of, observed_at=OBSERVED)


def test_only_empirically_verified_resolutions_are_enabled():
    assert RESOLUTION_SECONDS == {"1": 60, "60": 3600, "1D": 86400}


@pytest.mark.parametrize("resolution", ["5", "15", "180", "360", "720", "D"])
def test_unverified_or_mislabelled_resolutions_fail_closed(resolution):
    with pytest.raises(WallexCandleError, match="unsupported resolution"):
        parse_history(payload(), symbol="BTCUSDT", resolution=resolution,
                      as_of=datetime(2026, 10, 19, tzinfo=UTC), observed_at=OBSERVED)


def test_preserves_decimal_precision_and_source_time():
    candles = parse(payload(ts=(1792232400,), o=("100.000",), h=("102.0",), l=("99.00",), c=("101.500",), v=("0.123400",)))
    assert len(candles) == 1
    assert candles[0].open == Decimal("100.000")
    assert candles[0].volume == Decimal("0.123400")
    assert candles[0].source_timestamp == 1792232400
    assert candles[0].open_time == datetime.fromtimestamp(1792232400, UTC)
    assert candles[0].is_closed


def test_open_current_candle_is_excluded():
    ts = int(datetime(2026, 10, 17, 13, 2, tzinfo=UTC).timestamp())
    candles = parse(payload(ts=(ts,), o=("100",), h=("102",), l=("99",), c=("101",), v=("1",)))
    assert candles == ()


def test_missing_intervals_are_not_fabricated():
    ts = (1792232400, 1792232520)
    candles = parse(payload(ts=ts, o=("100", "101"), h=("102", "103"), l=("99", "100"), c=("101", "102"), v=("1", "2")))
    assert len(candles) == 2
    from datetime import timedelta
    assert candles[1].open_time - candles[0].open_time == timedelta(minutes=2)


def test_unequal_arrays_fail_closed():
    p = payload()
    p["c"] = ["101"]
    with pytest.raises(WallexCandleError, match="unequal lengths"):
        parse(p)


def test_invalid_ohlc_bounds_fail_closed():
    with pytest.raises(WallexCandleError, match="OHLC bounds"):
        parse(payload(ts=(1792232400,), o=("105",), h=("104",), l=("99",), c=("101",), v=("1",)))


def test_conflicting_duplicate_timestamp_fails_closed():
    with pytest.raises(WallexCandleError, match="conflicting duplicate"):
        parse(payload(ts=(1792232400,1792232400), o=("100","100"), h=("102","103"), l=("99","99"), c=("101","101"), v=("1","1")))


def test_non_monotonic_timestamps_fail_closed():
    with pytest.raises(WallexCandleError, match="not monotonic"):
        parse(payload(ts=(1792232460,1792232400)))


def test_no_data_status_is_not_misread_as_candles():
    with pytest.raises(WallexCandleError, match="source status"):
        parse({"s":"no_data"})


def test_empty_success_response_is_rejected_as_ambiguous():
    with pytest.raises(WallexCandleError, match="empty despite status ok"):
        parse({"s": "ok", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []})


def test_non_finite_numeric_value_is_rejected():
    with pytest.raises(WallexCandleError, match="finite"):
        parse(payload(ts=(1792232400,), o=("NaN",), h=("102",), l=("99",), c=("101",), v=("1",)))


def test_negative_volume_is_rejected():
    with pytest.raises(WallexCandleError, match="negative volume"):
        parse(payload(ts=(1792232400,), o=("100",), h=("102",), l=("99",), c=("101",), v=("-0.1",)))


def test_fetch_rejects_malformed_json(monkeypatch):
    import wallex_native_candles_v1 as adapter

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return b"not-json"

    monkeypatch.setattr(adapter, "urlopen", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(WallexCandleError, match="not valid JSON"):
        adapter.fetch_history(
            "BTCUSDT", "1",
            datetime(2026, 10, 17, 13, 0, tzinfo=UTC),
            datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
            as_of=datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
        )


def test_fetch_rejects_out_of_range_timestamp_even_if_candle_would_be_closed(monkeypatch):
    import json
    import wallex_native_candles_v1 as adapter

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return json.dumps({
                "s": "ok", "t": [1792232340],
                "o": ["100"], "h": ["102"], "l": ["99"], "c": ["101"], "v": ["1"],
            }).encode()

    monkeypatch.setattr(adapter, "urlopen", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(WallexCandleError, match="outside requested range"):
        adapter.fetch_history(
            "BTCUSDT", "1",
            datetime(2026, 10, 17, 13, 0, tzinfo=UTC),
            datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
            as_of=datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
        )


def test_future_observation_as_of_must_be_aware():
    with pytest.raises(WallexCandleError, match="as_of must be timezone-aware"):
        parse_history(payload(), symbol="BTCUSDT", resolution="1", as_of=datetime(2026,10,17), observed_at=OBSERVED)


def test_misaligned_timestamp_fails_closed():
    with pytest.raises(WallexCandleError, match="not aligned"):
        parse(payload(ts=(1792232401,), o=("100",), h=("102",), l=("99",), c=("101",), v=("1",)))


def test_identical_duplicate_timestamp_is_not_double_counted():
    p = payload(ts=(1792232400, 1792232400), o=("100", "100"), h=("102", "102"),
                l=("99", "99"), c=("101", "101"), v=("1", "1"))
    candles = parse(p)
    assert len(candles) == 1


def test_daily_candle_does_not_assume_utc_midnight_alignment():
    ts = 1792232400
    assert ts % 86400 != 0
    p = payload(ts=(ts,), o=("100",), h=("102",), l=("99",), c=("101",), v=("1",))
    candles = parse_history(p, symbol="BTCUSDT", resolution="1D",
                            as_of=datetime(2026, 10, 19, tzinfo=UTC), observed_at=OBSERVED)
    assert len(candles) == 1
    from datetime import timedelta
    assert candles[0].close_time == candles[0].open_time + timedelta(days=1)


def test_hourly_candle_alignment_uses_one_hour_buckets():
    ts = 1792231200
    p = payload(ts=(ts,), o=("100",), h=("102",), l=("99",), c=("101",), v=("1",))
    candles = parse_history(p, symbol="BTCUSDT", resolution="60",
                            as_of=datetime(2026, 10, 19, tzinfo=UTC), observed_at=OBSERVED)
    assert len(candles) == 1
    assert candles[0].close_time.timestamp() - candles[0].open_time.timestamp() == 3600


def test_fetch_decodes_fractional_json_numbers_as_decimal(monkeypatch):
    import wallex_native_candles_v1 as adapter

    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limit):
            return (b'{"s":"ok","t":[1792232400],"o":[100.000000000000000001],'
                    b'"h":[102.000000000000000001],"l":[99.000000000000000001],'
                    b'"c":[101.000000000000000001],"v":[0.123456789012345678901]}')

    monkeypatch.setattr(adapter, "urlopen", lambda *args, **kwargs: FakeResponse())
    candles = adapter.fetch_history(
        "BTCUSDT", "1",
        datetime(2026, 10, 17, 13, 0, tzinfo=UTC),
        datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
        as_of=datetime(2026, 10, 17, 13, 3, tzinfo=UTC),
    )
    assert candles[0].open == Decimal("100.000000000000000001")
    assert candles[0].volume == Decimal("0.123456789012345678901")
