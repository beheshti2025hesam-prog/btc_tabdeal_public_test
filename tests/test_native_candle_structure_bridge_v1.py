"""Native 15m OHLCV to the existing causal structure observation contract."""
from __future__ import annotations

import importlib.util
from dataclasses import replace
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from forward.native_candle_bridge_v1 import (
    normalize_native_candles,
    to_lightweight_chart_payload,
    to_structure_candles,
)
from forward.structure_observation_v1 import observe_closed_candles


def load_wallex():
    path = Path(os.environ["HES_WALLEX_ADAPTER_PATH"])
    spec = importlib.util.spec_from_file_location("chart_contract_wallex", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_binance():
    path = Path(os.environ["HES_BINANCE_ADAPTER_PATH"])
    spec = importlib.util.spec_from_file_location("structure_contract_binance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


binance = load_binance()
wallex = load_wallex()
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
    assert structure_rows[0].open == Decimal("100")
    assert structure_rows[0].volume is None  # structure is price-only; raw volume stays in batch
    assert structure_rows[0].trade_count is None
    assert structure_rows[0].first_sequence is None
    assert structure_rows[0].last_sequence is None
    assert structure_rows[0].source_first_observed_at is None
    assert structure_rows[0].source_last_observed_at is None

    observation = observe_closed_candles(structure_rows, observed_at=AS_OF)
    record = observation.as_record()
    assert record["symbol"] == "BTCUSDT"
    assert record["timeframe"] == "15m"
    assert record["venue"] == "binance"
    assert record["market"] == "usdm_futures"
    assert record["source"] == "binance_native_ohlcv"
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


def test_structure_observer_rejects_mixed_native_market_identity():
    rows = actual_binance_15m_rows()
    batch = normalize_native_candles(rows, venue="binance", market="usdm_futures", as_of=AS_OF)
    structure_rows = list(to_structure_candles(batch))
    structure_rows[1] = replace(structure_rows[1], market="spot")
    with pytest.raises(ValueError, match="mixed venue/market/source"):
        observe_closed_candles(structure_rows, observed_at=AS_OF)


def test_chart_projection_is_read_only_utc_and_omits_volume_by_default():
    rows = actual_binance_15m_rows()
    batch = normalize_native_candles(rows, venue="binance", market="usdm_futures", as_of=AS_OF)
    payload = to_lightweight_chart_payload(batch)
    assert payload["identity"] == {
        "venue": "binance",
        "market": "usdm_futures",
        "symbol": "BTCUSDT",
        "timeframe_seconds": 900,
        "source": "binance_native_ohlcv",
    }
    assert payload["timezone"] == "UTC"
    assert payload["volume_included"] is False
    assert payload["bars"][0]["time"] == int(START.timestamp())
    assert "volume" not in payload["bars"][0]
    assert payload["volume_bars"] == []
    assert payload["gaps"] == []

    with_volume = to_lightweight_chart_payload(batch, include_volume=True)
    assert "volume" not in with_volume["bars"][0]
    assert with_volume["volume_bars"][0] == {
        "time": int(START.timestamp()), "value": 12.34
    }
    assert with_volume["volume_semantics"] == "RAW_SOURCE_REPORTED"


def test_chart_projection_fails_closed_on_wallex_volume():
    start = START + timedelta(minutes=60)
    as_of = start + timedelta(minutes=1)
    rows = wallex.parse_history(
        {"s": "ok", "t": [int(start.timestamp())], "o": ["100.10"],
         "h": ["103.00"], "l": ["99.50"], "c": ["102.20"], "v": ["12.3400"]},
        symbol="BTCUSDT", timeframe_minutes=1, as_of=as_of,
    )
    batch = normalize_native_candles(rows, venue="wallex", market="spot", as_of=as_of)
    payload = to_lightweight_chart_payload(batch)
    assert payload["volume_included"] is False
    assert "volume" not in payload["bars"][0]
    with pytest.raises(ValueError, match="wallex_volume_semantics_unresolved"):
        to_lightweight_chart_payload(batch, include_volume=True)


def test_wallex_spot_parser_output_cannot_be_relabelled_as_futures():
    start = START + timedelta(minutes=60)
    as_of = start + timedelta(minutes=1)
    rows = wallex.parse_history(
        {"s": "ok", "t": [int(start.timestamp())], "o": ["100.10"],
         "h": ["103.00"], "l": ["99.50"], "c": ["102.20"], "v": ["12.3400"]},
        symbol="BTCUSDT", timeframe_minutes=1, as_of=as_of,
    )
    with pytest.raises(ValueError, match="source_market_mismatch"):
        normalize_native_candles(rows, venue="wallex", market="usdm_futures", as_of=as_of)


def test_wallex_native_hourly_candles_project_to_chart_payload_without_volume():
    start = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
    close = start + timedelta(hours=1)
    rows = wallex.parse_history(
        {"s": "ok", "t": [int(start.timestamp())], "o": ["100.10"],
         "h": ["103.00"], "l": ["99.50"], "c": ["102.20"], "v": ["24.6800"]},
        symbol="BTCUSDT", timeframe_minutes=60, as_of=close,
    )
    batch = normalize_native_candles(rows, venue="wallex", market="spot", as_of=close)
    payload = to_lightweight_chart_payload(batch)

    assert payload["identity"] == {
        "venue": "wallex",
        "market": "spot",
        "symbol": "BTCUSDT",
        "timeframe_seconds": 3600,
        "source": "wallex_native_udf_history",
    }
    assert payload["timezone"] == "UTC"
    assert payload["bars"] == [{
        "time": int(start.timestamp()),
        "open": 100.1,
        "high": 103.0,
        "low": 99.5,
        "close": 102.2,
    }]
    assert payload["volume_included"] is False
    assert payload["volume_bars"] == []
    assert payload["gaps"] == []
    assert payload["discarded_open_candles"] == 0
