"""Contract tests against the exact native adapter revisions used by HES.

The workflow checks out adapter source at immutable commit SHAs into isolated
subdirectories. No network calls are made; parser outputs are passed directly
to the production bridge normalizer.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from forward.native_candle_bridge_v1 import normalize_native_candles, to_feature_candles


def load_module(name: str, env_name: str):
    path = Path(os.environ[env_name])
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


wallex = load_module("contract_native_wallex", "HES_WALLEX_ADAPTER_PATH")
binance = load_module("contract_native_binance", "HES_BINANCE_ADAPTER_PATH")

START = datetime(2026, 10, 19, 10, 0, tzinfo=timezone.utc)
AS_OF = START + timedelta(minutes=1)


def wallex_candles():
    payload = {
        "s": "ok",
        "t": [int(START.timestamp())],
        "o": ["100.10"],
        "h": ["103.00"],
        "l": ["99.50"],
        "c": ["102.20"],
        "v": ["12.3400"],
    }
    return wallex.parse_history(
        payload, symbol="BTCUSDT", timeframe_minutes=1, as_of=AS_OF
    )


def binance_candles(market="spot"):
    open_ms = int(START.timestamp() * 1000)
    row = [
        open_ms, "100.10", "103.00", "99.50", "102.20", "12.3400",
        open_ms + 59_999, "1260.00", 17, "7.0000", "714.00", "0",
    ]
    return binance.parse_klines(
        [row], market=market, symbol="BTCUSDT", interval="1m",
        as_of_ms=open_ms + 60_000, retrieved_at=AS_OF,
        raw_payload=b'[[native fixture]]',
    ).candles


@pytest.mark.parametrize(
    ("adapter_rows", "venue", "market"),
    [
        (wallex_candles, "wallex", "spot"),
        (lambda: binance_candles("spot"), "binance", "spot"),
        (lambda: binance_candles("usdm_futures"), "binance", "usdm_futures"),
    ],
)
def test_real_adapter_output_normalizes_into_hes_features(adapter_rows, venue, market):
    rows = adapter_rows()
    batch = normalize_native_candles(
        rows, venue=venue, market=market, as_of=AS_OF
    )
    assert batch.identity.venue == venue
    assert batch.identity.market == market
    assert batch.identity.symbol == "BTCUSDT"
    assert batch.identity.timeframe_seconds == 60
    assert len(batch.candles) == 1
    candle = batch.candles[0]
    assert candle.start == START
    assert candle.end == AS_OF  # exclusive end, regardless of source convention
    assert str(candle.open) == "100.10"
    assert str(candle.volume) == "12.3400"
    assert not batch.gaps
    assert batch.discarded_open_candles == 0

    feature_rows = to_feature_candles(batch)
    assert len(feature_rows) == 1
    assert feature_rows[0].trade_count is None
    assert feature_rows[0].timeframe_seconds == 60
    assert feature_rows[0].close == pytest.approx(102.2)
    assert feature_rows[0].volume is None
    with pytest.raises(ValueError, match="wallex_volume_semantics_unresolved"):
        to_feature_candles(batch, include_volume=True)


def test_binance_market_identity_mismatch_fails_closed():
    rows = binance_candles("spot")
    with pytest.raises(ValueError, match="mixed_market"):
        normalize_native_candles(
            rows, venue="binance", market="usdm_futures", as_of=AS_OF
        )


def test_native_adapter_output_keeps_closed_bar_boundary_contract():
    wallex_row = wallex_candles()[0]
    binance_row = binance_candles()[0]
    assert wallex_row.close_time == AS_OF
    assert binance_row.close_time_ms == int(AS_OF.timestamp() * 1000) - 1


def test_wallex_spot_adapter_cannot_be_relabelled_as_futures():
    rows = wallex_candles()
    with pytest.raises(ValueError, match="source_market_mismatch"):
        normalize_native_candles(
            rows, venue="wallex", market="usdm_futures", as_of=AS_OF
        )
