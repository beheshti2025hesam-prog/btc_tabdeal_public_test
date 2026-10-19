"""Native 15m OHLCV to the existing causal structure observation contract."""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from forward.native_candle_bridge_v1 import normalize_native_candles, to_structure_candles
from forward.structure_observation_v1 import observe_closed_candles


def load_binance():
    path = Path(os.environ["HES_BINANCE_ADAPTER_PATH"])
    spec = importlib.util.spec_from_file_location("structure_contract_binance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


binance = load_binance()
START = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
AS_OF = START + timedelta(minutes=105)


def actual_binance_15m_rows():
    rows = []
    for i in range(7):
        open_ms = int((START + timedelta(minutes=15 * i)).timestamp() * 1000)
        # Deliberately varied OHLC, while maintaining valid bounds.
        o = 100 + i
        c = 101 + i
        h = c + (3 if i == 3 else 1)
        low = o - (2 if i == 3 else 1)
        rows.append([
            open_ms, str(o), str(h), str(low), str(c), "12.3400",
            open_ms + 899_999, "1260.00", 17, "7.0000", "714.00", "0",
        ])
    return binance.parse_klines(
        rows, market="usdm_futures", symbol="BTCUSDT", interval="15m",
        as_of_ms=int(AS_OF.timestamp() * 1000),
        retrieved_at=AS_OF, raw_payload=b"offline-15m-structure-fixture",
    ).candles


def test_real_binance_15m_parser_output_reaches_existing_structure_observer():
    source_rows = actual_binance_15m_rows()
    batch = normalize_native_candles(
        source_rows, venue="binance", market="usdm_futures", as_of=AS_OF
    )
    structure_rows = to_structure_candles(batch)

    assert len(structure_rows) == 7
    assert structure_rows[0].open_time == START
    assert structure_rows[0].close_time == START + timedelta(minutes=15)
    assert structure_rows[0].open == pytest.approx(100)  # Decimal compares numerically
    assert structure_rows[0].volume == source_rows[0].volume
    assert structure_rows[0].trade_count is None
    assert structure_rows[0].first_sequence is None
    assert structure_rows[0].last_sequence is None
    assert structure_rows[0].source_first_observed_at is None
    assert structure_rows[0].source_last_observed_at is None

    observation = observe_closed_candles(structure_rows, observed_at=AS_OF)
    record = observation.as_record()
    assert record["symbol"] == "BTCUSDT"
    assert record["timeframe"] == "15m"
    assert record["closed_candle_count"] == 7
    assert record["observed_at"] == AS_OF.isoformat()
    assert record["status"] in {"STRUCTURE_OBSERVED", "UNKNOWN_NO_CONFIRMED_SWINGS"}


def test_structure_bridge_rejects_non_15m_native_batch():
    rows = actual_binance_15m_rows()[:1]
    one_minute_rows = binance.parse_klines(
        [[int(START.timestamp() * 1000), "100", "102", "99", "101", "1",
          int(START.timestamp() * 1000) + 59_999, "101", 1, "1", "101", "0"]],
        market="usdm_futures", symbol="BTCUSDT", interval="1m",
        as_of_ms=int((START + timedelta(minutes=1)).timestamp() * 1000),
        retrieved_at=START + timedelta(minutes=1), raw_payload=b"offline-1m",
    ).candles
    batch = normalize_native_candles(
        one_minute_rows, venue="binance", market="usdm_futures",
        as_of=START + timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="requires_15m"):
        to_structure_candles(batch)
