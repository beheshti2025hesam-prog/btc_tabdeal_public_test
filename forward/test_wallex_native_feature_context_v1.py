from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from forward.wallex_native_candles_v1 import NativeCandle
from forward.wallex_candle_observation_v1 import WallexCandleObservationV1
from forward.wallex_native_feature_context_v1 import (
    WallexFeatureContextError, build_wallex_feature_context_v1,
)

UTC = timezone.utc
AS_OF = datetime(2026, 10, 17, 13, 5, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 17, 13, 4, 59, tzinfo=UTC)
BASE_TS = int(datetime(2026, 10, 17, 13, 0, tzinfo=UTC).timestamp())


def candle(ts=BASE_TS, *, close="101", symbol="BTCUSDT", observed=OBSERVED):
    opened = datetime.fromtimestamp(ts, UTC)
    return NativeCandle(
        venue="wallex", symbol=symbol, resolution="1",
        open_time=opened, close_time=opened + timedelta(minutes=1),
        open=Decimal("100"), high=Decimal("102"), low=Decimal("99"),
        close=Decimal(close), volume=Decimal("0.1"),
        source_timestamp=ts, source_observed_at=observed,
    )


def observation(tmp_path, items=None, as_of=AS_OF, max_age=600):
    return WallexCandleObservationV1(tmp_path / "observation.jsonl").observe(
        items or [candle(), candle(BASE_TS + 60, close="102")],
        as_of=as_of, run_id="feature-contract-test", max_age_seconds=max_age,
    )


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def resign_candle(c):
    body = {k: v for k, v in c.items() if k != "canonical_candle_sha256"}
    c["canonical_candle_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest()


def resign_record(record):
    body = {k: v for k, v in record.items() if k != "record_sha256"}
    record["record_sha256"] = hashlib.sha256(canonical(body).encode()).hexdigest()


def test_valid_record_yields_descriptive_context_only(tmp_path):
    record = observation(tmp_path)
    context = build_wallex_feature_context_v1(record, as_of=AS_OF)
    assert context["status"] == "FEATURE_CONTEXT_OBSERVED_RESEARCH_ONLY"
    assert context["timeframe"] == "1m"
    assert context["input_candle_count"] == 2
    assert context["features"]["directional_context_last_two"] == "UP_CONTEXT"
    assert context["sequence_semantics"] == "NOT_APPLICABLE_NATIVE_OHLCV"
    assert context["raw_source_replay_verified"] is False
    assert context["signal_generated"] is False
    assert context["trade_decision_generated"] is False
    assert context["execution_enabled"] is False


def test_record_hash_tampering_fails_closed(tmp_path):
    record = observation(tmp_path)
    record["symbol"] = "ETHUSDT"
    with pytest.raises(WallexFeatureContextError, match="record hash mismatch"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_candle_hash_tampering_fails_closed(tmp_path):
    record = observation(tmp_path)
    record["candles"][0]["close"] = "100.5"
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="canonical hash mismatch"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_hash_valid_but_semantically_invalid_source_timestamp_fails(tmp_path):
    record = observation(tmp_path)
    record["candles"][0]["source_timestamp"] += 1
    resign_candle(record["candles"][0])
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="source timestamp mismatch"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_hash_valid_scope_mismatch_fails(tmp_path):
    record = observation(tmp_path)
    record["candles"][0]["symbol"] = "ETHUSDT"
    resign_candle(record["candles"][0])
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="scope mismatch"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_hash_valid_gap_fails_even_if_status_is_forged_observed(tmp_path):
    record = observation(tmp_path)
    record["candles"][1]["open_time"] = (datetime.fromtimestamp(BASE_TS + 120, UTC)).isoformat()
    record["candles"][1]["close_time"] = (datetime.fromtimestamp(BASE_TS + 180, UTC)).isoformat()
    record["candles"][1]["source_timestamp"] = BASE_TS + 120
    resign_candle(record["candles"][1])
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="missing intervals"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_blocked_gap_record_cannot_be_consumed(tmp_path):
    record = observation(tmp_path, [candle(), candle(BASE_TS + 120)])
    assert record["status"] == "BLOCKED"
    with pytest.raises(WallexFeatureContextError, match="OBSERVED records"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_future_observation_is_rejected(tmp_path):
    record = observation(tmp_path)
    record["observed_at"] = (AS_OF + timedelta(seconds=1)).isoformat()
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="future"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_stale_candles_are_rejected_even_if_original_record_was_fresh(tmp_path):
    record = observation(tmp_path)
    with pytest.raises(WallexFeatureContextError, match="stale"):
        build_wallex_feature_context_v1(record, as_of=AS_OF + timedelta(minutes=20))


def test_unsupported_timeframe_and_sequence_contract_are_not_inferred(tmp_path):
    record = observation(tmp_path)
    record["resolution"] = "15"
    record["timeframe"] = "15m"
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="unsupported native resolution"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_wrong_venue_and_symbol_fail_closed(tmp_path):
    record = observation(tmp_path)
    record["venue"] = "tabdeal"
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="unsupported venue"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)
    record = observation(tmp_path)
    record["symbol"] = "ETHUSDT"
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="unsupported symbol"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_raw_response_hash_cannot_be_claimed_without_raw_capture(tmp_path):
    record = observation(tmp_path)
    record["source_provenance"]["raw_response_sha256"] = "a" * 64
    resign_record(record)
    with pytest.raises(WallexFeatureContextError, match="raw-response hash claim"):
        build_wallex_feature_context_v1(record, as_of=AS_OF)


def test_historical_window_bars_are_not_mistaken_for_stale_latest_data(tmp_path):
    as_of = datetime(2026, 10, 17, 13, 20, tzinfo=UTC)
    observed = as_of
    items = [candle(BASE_TS + i * 60, close=str(100 + i), observed=observed)
             for i in range(20)]
    record = observation(tmp_path, items, as_of=as_of, max_age=60)
    context = build_wallex_feature_context_v1(record, as_of=as_of)
    assert context["input_candle_count"] == 20
    assert context["status"] == "FEATURE_CONTEXT_OBSERVED_RESEARCH_ONLY"
