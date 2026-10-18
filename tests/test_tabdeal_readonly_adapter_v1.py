from datetime import datetime, timezone
import pytest

from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


def base():
    return {
        "type": "trade",
        "symbol": "BTC_USDT",
        "price": "100",
        "amount": "0.1",
        "side": "buy",
        "sequence": 7,
        "timestamp": 1791356400000,
    }


def test_normalizes_frame():
    record = parse_trade_frame(base(), as_of=ASOF)
    assert record["source"] == "tabdeal_ws_forward_v1"
    assert record["sequence"] == 7


def test_rejects_future():
    frame = base()
    frame["timestamp"] = 1791356401000
    with pytest.raises(ValueError, match="future"):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_scope_and_incomplete():
    frame = base()
    frame["symbol"] = "ETH_USDT"
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)
    frame = base()
    del frame["sequence"]
    with pytest.raises(ValueError):
        parse_trade_frame(frame, as_of=ASOF)


def test_rejects_bad_values():
    for key, value in [("price", "0"), ("amount", "-1"), ("side", "hold"), ("sequence", -1)]:
        frame = base()
        frame[key] = value
        with pytest.raises(ValueError):
            parse_trade_frame(frame, as_of=ASOF)


def test_rejects_boolean_float_and_non_ascii_sequence_wire_values():
    for value in (True, False, 7.0, 7.5, float("nan"), float("inf"), " 7", "7 ", "7.0", "٧", ""):
        frame = base()
        frame["sequence"] = value
        with pytest.raises(ValueError, match="invalid sequence"):
            parse_trade_frame(frame, as_of=ASOF)


def test_rejects_boolean_and_nonfinite_timestamp_wire_values():
    for value in (True, False, float("nan"), float("inf")):
        frame = base()
        frame["timestamp"] = value
        with pytest.raises(ValueError, match="invalid timestamp"):
            parse_trade_frame(frame, as_of=ASOF)


@pytest.mark.parametrize(
    "timestamp",
    [
        1791354600,                 # Unix seconds
        1791354600000,              # Unix milliseconds
        1791354600000000,            # Unix microseconds
        "2026-10-07T06:30:00Z",     # RFC3339 UTC
        "2026-10-07T08:30:00+02:00",  # Offset-aware equivalent
    ],
)
def test_timestamp_units_and_offsets_normalize_to_same_utc(timestamp):
    frame = base()
    frame["timestamp"] = timestamp
    record = parse_trade_frame(frame, as_of=ASOF)
    assert record["source_updated"] == "2026-10-07T06:30:00+00:00"


def test_naive_timestamp_string_is_rejected():
    frame = base()
    frame["timestamp"] = "2026-10-07T06:30:00"
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_trade_frame(frame, as_of=ASOF)


def test_transport_payload_digest_survives_normalization_and_exact_replay_is_detected():
    from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1

    frame = base()
    frame["timestamp"] = 1791354600000  # 06:30 UTC; the 06:30 candle is closed by ASOF.
    frame["raw_payload_sha256"] = "a" * 64
    record = parse_trade_frame(frame, as_of=ASOF)
    assert record["raw_payload_sha256"] == "a" * 64

    result = SequenceAwareCandleIngestionV1().ingest([record, dict(record)], as_of=ASOF)
    assert [event.status for event in result.events] == ["ACCEPTED", "EXACT_REPLAY"]
    assert len(result.candles) == 1
    assert result.candles[0].trade_count == 1
