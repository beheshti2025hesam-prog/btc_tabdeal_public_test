from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from forward.native_ohlcv_forward_runner_v1 import NativeOHLCVForwardRunnerV1
from forward.native_ohlcv_feature_pipeline_v1 import NativeOHLCVFeaturePipelineV1

OPEN = 1_760_000_400_000
FETCHED = OPEN + 900_100


def sample_batch(*, count=1, gaps=(), close_time=None, fetched_at_ms=None):
    candles = []
    for index in range(count):
        open_time = OPEN + index * 900_000
        close_at = close_time if count == 1 and close_time is not None else open_time + 899_999
        close = Decimal(str(100 + index))
        high = max(Decimal("102.00"), close)
        candles.append(SimpleNamespace(
            venue="binance", product="spot", symbol="BTCUSDT", interval="15m",
            open_time_ms=open_time, close_time_ms=close_at,
            open=Decimal("100.00"), high=high, low=Decimal("99.00"), close=close,
            volume=Decimal("2.500"), quote_volume=Decimal("250.625"),
            trade_count=12, taker_buy_volume=Decimal("1.600"),
            taker_buy_quote_volume=Decimal("160.400"), closed=True,
        ))
    fetched = fetched_at_ms if fetched_at_ms is not None else OPEN + count * 900_000 + 100
    return SimpleNamespace(
        venue="binance", product="spot", symbol="BTCUSDT", interval="15m",
        endpoint_kind="uiKlines", fetched_at_ms=fetched, response_sha256="a" * 64,
        candles=tuple(candles), gaps=tuple(gaps), open_candles_excluded=1,
    )


class FakeSource:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def fetch(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


def test_disabled_runner_does_not_fetch_or_write(tmp_path):
    source = FakeSource(sample_batch())
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal)
    result = runner.run_once(symbol="BTCUSDT", run_id="run-disabled")
    assert result.status == "BLOCKED"
    assert result.reason == "NATIVE_OHLCV_RUNNER_DISABLED"
    assert source.calls == []
    assert not journal.exists()


def test_enabled_runner_records_one_validated_native_batch_without_sequence(tmp_path):
    source = FakeSource(sample_batch())
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal, enabled=True)
    result = runner.run_once(symbol="BTCUSDT", interval="15m", limit=5, run_id="run-native")
    stored = json.loads(journal.read_text(encoding="utf-8"))
    assert result.status == "NATIVE_OHLCV_BATCH_OBSERVED"
    assert result.candle_count == 1 and result.gap_count == 0
    assert result.journal_digest
    assert stored["event_id"] == f"run-native:batch:{FETCHED}"
    assert stored["source"] == "binance_native_ohlcv_v1"
    assert stored["source_response_sha256"] == "a" * 64
    assert stored["candles"][0]["open"] == "100.00"
    assert stored["candles"][0]["volume"] == "2.500"
    assert "sequence" not in stored and "outcome" not in stored
    assert stored["execution"] == "OFF"
    assert stored["native_features"]["decision_ready"] is False
    assert stored["native_features"]["snapshot"] is None
    assert result.feature_ready is False


def test_unclosed_candle_is_blocked_before_any_journal_write(tmp_path):
    source = FakeSource(sample_batch(close_time=FETCHED))
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal, enabled=True)
    result = runner.run_once(symbol="BTCUSDT", run_id="run-open-candle")
    assert result.status == "BLOCKED"
    assert result.reason.startswith("NATIVE_OHLCV_SOURCE_INVALID:")
    assert not journal.exists()


def test_fetch_failure_is_blocked_without_partial_observation(tmp_path):
    source = FakeSource(error=TimeoutError())
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal, enabled=True)
    result = runner.run_once(symbol="BTCUSDT", run_id="run-source-error")
    assert result.status == "BLOCKED"
    assert result.reason == "NATIVE_OHLCV_SOURCE_INVALID:TimeoutError"
    assert not journal.exists()


def test_gaps_are_journaled_explicitly_without_fabricated_candles(tmp_path):
    gap = SimpleNamespace(
        expected_open_time_ms=OPEN + 900_000,
        next_observed_open_time_ms=OPEN + 2_700_000,
        missing_intervals=2,
    )
    source = FakeSource(sample_batch(gaps=(gap,)))
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal, enabled=True)
    result = runner.run_once(symbol="BTCUSDT", run_id="run-gap")
    stored = json.loads(journal.read_text(encoding="utf-8"))
    assert result.status == "NATIVE_OHLCV_GAPS_PRESENT"
    assert len(stored["candles"]) == 1
    assert stored["gaps"][0]["missing_intervals"] == 2


def test_future_fetch_timestamp_is_blocked_before_journaling(tmp_path):
    import time
    source = FakeSource(sample_batch(fetched_at_ms=int(time.time() * 1000) + 120_000))
    journal = tmp_path / "observations.jsonl"
    runner = NativeOHLCVForwardRunnerV1(source=source, journal_path=journal, enabled=True)
    result = runner.run_once(symbol="BTCUSDT", run_id="run-future-fetch")
    assert result.status == "BLOCKED"
    assert result.reason == "NATIVE_OHLCV_SOURCE_INVALID:ValueError"
    assert not journal.exists()


def test_runner_journals_native_feature_snapshot_from_the_same_fetched_batch(tmp_path):
    source = FakeSource(sample_batch(count=3))
    journal = tmp_path / "observations.jsonl"
    pipeline = NativeOHLCVFeaturePipelineV1(ema_period=3, vwap_period=3, momentum_period=2)
    runner = NativeOHLCVForwardRunnerV1(
        source=source, journal_path=journal, enabled=True, feature_pipeline=pipeline
    )
    result = runner.run_once(symbol="BTCUSDT", interval="15m", limit=3, run_id="run-native-features")
    stored = json.loads(journal.read_text(encoding="utf-8"))
    assert result.status == "NATIVE_OHLCV_BATCH_OBSERVED"
    assert result.feature_ready
    assert result.feature_reason == "NATIVE_OHLCV_FEATURES_READY"
    assert stored["native_features"]["decision_ready"] is True
    assert stored["native_features"]["snapshot"]["vwap"] == 100.25
    assert stored["native_features"]["snapshot"]["buy_ratio"] == 0.64
    assert stored["source_response_sha256"] == "a" * 64
    assert stored["execution"] == "OFF"
