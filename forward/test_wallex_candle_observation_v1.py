from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from forward.wallex_native_candles_v1 import NativeCandle
from forward.clean_structure_context_v1 import CleanStructureContextV1
from forward.wallex_candle_observation_v1 import (
    WallexCandleObservationV1, WallexObservationError,
)

UTC = timezone.utc
AS_OF = datetime(2026, 10, 17, 13, 5, tzinfo=UTC)
OBSERVED = datetime(2026, 10, 17, 13, 4, 59, tzinfo=UTC)


def candle(ts=1792232400, *, resolution="1", observed=OBSERVED, close=None, symbol="BTCUSDT"):
    step = {"1": 60, "60": 3600, "1D": 86400}[resolution]
    opened = datetime.fromtimestamp(ts, UTC)
    return NativeCandle(
        venue="wallex", symbol=symbol, resolution=resolution,
        open_time=opened, close_time=opened + timedelta(seconds=step),
        open=Decimal("100.000"), high=Decimal("102"), low=Decimal("99"),
        close=Decimal("101"), volume=Decimal("0.1234"),
        source_timestamp=ts, source_observed_at=observed,
    )


def test_valid_closed_candles_are_journaled_and_feature_bridge_stays_blocked(tmp_path):
    path = tmp_path / "wallex.jsonl"
    items = [candle(), candle(1792232460)]
    record = WallexCandleObservationV1(path).observe(
        items, as_of=AS_OF, run_id="run-1", max_age_seconds=600,
    )
    assert record["status"] == "OBSERVED"
    assert record["timeframe"] == "1m"
    assert len(record["candles"]) == 2
    assert record["downstream_features"]["status"] == "BLOCKED_CONTRACT_MISMATCH"
    assert record["downstream_features"]["synthetic_candles_created"] is False
    assert record["source_provenance"]["raw_response_bytes_retained"] is False
    assert record["source_provenance"]["raw_response_sha256"] is None
    assert len(record["record_sha256"]) == 64
    assert path.read_bytes().endswith(b"\n")


def test_missing_interval_is_explicit_and_blocks_promotion(tmp_path):
    record = WallexCandleObservationV1(tmp_path / "gaps.jsonl").observe(
        [candle(), candle(1792232580)], as_of=AS_OF, run_id="gap", max_age_seconds=600,
    )
    assert record["status"] == "BLOCKED"
    assert record["reason"] == "MISSING_INTERVALS"
    assert record["gaps"][0]["missing_intervals"] == 1
    assert len(record["candles"]) == 2


def test_stale_latest_candle_blocks(tmp_path):
    record = WallexCandleObservationV1(tmp_path / "stale.jsonl").observe(
        [candle(observed=AS_OF)],
        as_of=AS_OF + timedelta(minutes=20), run_id="stale", max_age_seconds=600,
    )
    assert record["status"] == "BLOCKED"
    assert "stale" in record["reason"].lower()


def test_open_candle_is_rejected(tmp_path):
    item = candle(ts=int(AS_OF.timestamp()) - 30)
    with pytest.raises(WallexObservationError, match="open or future"):
        WallexCandleObservationV1(tmp_path / "open.jsonl").observe(
            [item], as_of=AS_OF, run_id="open", max_age_seconds=600,
        )


def test_mixed_resolution_or_symbol_is_rejected(tmp_path):
    with pytest.raises(WallexObservationError, match="mixed venue"):
        WallexCandleObservationV1(tmp_path / "mixed.jsonl").observe(
            [candle(), candle(1792232460, symbol="ETHUSDT")],
            as_of=AS_OF, run_id="mixed", max_age_seconds=600,
        )


def test_conflicting_duplicate_timestamp_is_rejected(tmp_path):
    first = candle()
    conflict = replace(first, close=Decimal("100.5"))
    with pytest.raises(WallexObservationError, match="conflicting duplicate"):
        WallexCandleObservationV1(tmp_path / "dup.jsonl").observe(
            [first, conflict], as_of=AS_OF, run_id="dup", max_age_seconds=600,
        )


def test_identical_duplicate_is_collapsed(tmp_path):
    record = WallexCandleObservationV1(tmp_path / "same.jsonl").observe(
        [candle(), candle()], as_of=AS_OF, run_id="same", max_age_seconds=600,
    )
    assert len(record["candles"]) == 1


def test_non_monotonic_input_is_rejected(tmp_path):
    with pytest.raises(WallexObservationError, match="not monotonic"):
        WallexCandleObservationV1(tmp_path / "order.jsonl").observe(
            [candle(1792232460), candle()], as_of=AS_OF, run_id="order", max_age_seconds=600,
        )


def test_hash_valid_payload_mutation_is_detected(tmp_path):
    path = tmp_path / "mutate.jsonl"
    observer = WallexCandleObservationV1(path)
    observer.observe([candle()], as_of=AS_OF, run_id="first", max_age_seconds=600)
    row = json.loads(path.read_text())
    row["candles"][0]["close"] = "999"
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(WallexObservationError, match="payload/hash mismatch"):
        observer.observe([candle(1792232460)], as_of=AS_OF, run_id="second", max_age_seconds=600)


def test_row_deletion_or_reordering_is_detected(tmp_path):
    path = tmp_path / "chain.jsonl"
    observer = WallexCandleObservationV1(path)
    observer.observe([candle()], as_of=AS_OF, run_id="one", max_age_seconds=600)
    observer.observe([candle(1792232460)], as_of=AS_OF, run_id="two", max_age_seconds=600)
    rows = path.read_text().splitlines()
    path.write_text(rows[1] + "\n")
    with pytest.raises(WallexObservationError, match="chain mismatch"):
        observer.observe([candle(1792232520)], as_of=AS_OF, run_id="three", max_age_seconds=600)


def test_truncated_final_line_is_detected(tmp_path):
    path = tmp_path / "truncated.jsonl"
    observer = WallexCandleObservationV1(path)
    observer.observe([candle()], as_of=AS_OF, run_id="one", max_age_seconds=600)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(WallexObservationError, match="incomplete final line"):
        observer.observe([candle(1792232460)], as_of=AS_OF, run_id="two", max_age_seconds=600)


def test_bad_hash_chain_is_not_extended(tmp_path):
    path = tmp_path / "bad-chain.jsonl"
    observer = WallexCandleObservationV1(path)
    observer.observe([candle()], as_of=AS_OF, run_id="one", max_age_seconds=600)
    row = json.loads(path.read_text())
    row["previous_record_sha256"] = "f" * 64
    path.write_text(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(WallexObservationError, match="chain mismatch"):
        observer.observe([candle(1792232460)], as_of=AS_OF, run_id="two", max_age_seconds=600)


def test_legacy_feature_consumer_rejects_native_wallex_scope():
    native = {"symbol": "BTCUSDT", "timeframe": "1m", "status": "CLOSED",
              "open": "100", "high": "102", "low": "99", "close": "101"}
    with pytest.raises(ValueError, match="unsupported scope"):
        CleanStructureContextV1().observe([native, native])
