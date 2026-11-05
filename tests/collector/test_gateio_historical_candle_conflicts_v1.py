from __future__ import annotations

from copy import deepcopy

import pytest
from pathlib import Path

from scripts.reconcile_gateio_historical_candle_conflicts_v1 import (
    APPROVED,
    reconcile_rows,
    resolve_runtime_root,
    validate_three_snapshots,
)


def test_immutable_release_resolves_external_runtime_data_root(monkeypatch):
    monkeypatch.delenv("HES_GLOBAL_MARKET_DATA_ROOT", raising=False)
    release = Path("/opt/hes-trade-agent/releases/abc123")
    assert resolve_runtime_root(release) == Path("/opt/hes-trade-agent")


def test_explicit_runtime_data_root_override_is_respected(monkeypatch):
    monkeypatch.setenv("HES_GLOBAL_MARKET_DATA_ROOT", "/srv/hes-runtime")
    release = Path("/opt/hes-trade-agent/releases/abc123")
    assert resolve_runtime_root(release) == Path("/srv/hes-runtime")


def candle(timeframe: str, open_time: int, values: dict[str, str]) -> dict:
    seconds = 3600 if timeframe == "1h" else 14400
    return {
        "schema": "hes_global_candle_v1",
        "source": "gateio_public_spot",
        "symbol": "BTC_USDT",
        "timeframe": timeframe,
        "open_time": open_time,
        "close_time": open_time + seconds,
        **values,
        "closed": True,
        "observed_at": "2026-11-05T11:00:00+00:00",
    }


@pytest.mark.parametrize(
    ("timeframe", "open_time"),
    [(tf, ts) for tf, rows in APPROVED.items() for ts in rows],
)
def test_only_six_pinned_historical_conflicts_can_be_reconciled(timeframe, open_time):
    evidence = APPROVED[timeframe][open_time]
    old = candle(timeframe, open_time, evidence["old"])
    current = candle(timeframe, open_time, evidence["new"])

    merged, changes, added = reconcile_rows(timeframe, [old], [current])

    assert len(merged) == 1
    assert merged[0]["open_time"] == open_time
    assert merged[0]["close"] == evidence["new"]["close"]
    assert len(changes) == 1
    assert changes[0]["old"] == evidence["old"]
    assert changes[0]["new"] == evidence["new"]
    assert added == []


def test_reconciliation_aborts_if_any_pinned_conflict_identity_is_missing():
    timeframe, open_time = "1h", 1793170800
    other = candle(timeframe, open_time + 3600, {
        "open": "100", "high": "102", "low": "99", "close": "101",
        "volume": "1", "quote_volume": "100",
    })

    with pytest.raises(ValueError, match="pinned 1h conflict candle is missing"):
        reconcile_rows(timeframe, [other], [other])


def test_unapproved_historical_conflict_fails_closed():
    timeframe = "1h"
    open_time = 1793170800 + 7200
    old = candle(timeframe, open_time, {
        "open": "100", "high": "102", "low": "99", "close": "101",
        "volume": "1", "quote_volume": "100",
    })
    changed = deepcopy(old)
    changed["close"] = "101.1"

    with pytest.raises(ValueError, match="Unapproved"):
        reconcile_rows(timeframe, [old], [changed])


def test_pinned_conflict_aborts_if_live_value_no_longer_matches_old_evidence():
    timeframe, open_time = "1h", 1793170800
    old = candle(timeframe, open_time, APPROVED[timeframe][open_time]["old"])
    old["close"] = "81088.2"
    current = candle(timeframe, open_time, APPROVED[timeframe][open_time]["new"])

    with pytest.raises(ValueError, match="pinned old evidence"):
        reconcile_rows(timeframe, [old], [current])


def test_pinned_conflict_aborts_if_rest_value_no_longer_matches_three_probe_evidence():
    timeframe, open_time = "1h", 1793170800
    old = candle(timeframe, open_time, APPROVED[timeframe][open_time]["old"])
    current_values = dict(APPROVED[timeframe][open_time]["new"])
    current_values["close"] = "81088.5"
    current = candle(timeframe, open_time, current_values)

    with pytest.raises(ValueError, match="pinned three-probe evidence"):
        reconcile_rows(timeframe, [old], [current])


def test_reconciliation_preserves_history_and_adds_new_closed_rows():
    timeframe = "1h"
    ts = 1793170800
    seconds = 3600
    before = candle(timeframe, ts - seconds, {
        "open": "100", "high": "102", "low": "99", "close": "101",
        "volume": "1", "quote_volume": "100",
    })
    conflict_old = candle(timeframe, ts, APPROVED[timeframe][ts]["old"])
    middle = candle(timeframe, ts + seconds, {
        "open": "101", "high": "103", "low": "100", "close": "102",
        "volume": "2", "quote_volume": "200",
    })
    new_row = candle(timeframe, ts + 2 * seconds, {
        "open": "102", "high": "104", "low": "101", "close": "103",
        "volume": "3", "quote_volume": "300",
    })
    rest_conflict = candle(timeframe, ts, APPROVED[timeframe][ts]["new"])
    rest_middle = deepcopy(middle)
    rest_new = deepcopy(new_row)

    merged, changes, added = reconcile_rows(
        timeframe, [before, conflict_old, middle], [rest_conflict, rest_middle, rest_new]
    )

    assert [row["open_time"] for row in merged] == [
        ts - seconds, ts, ts + seconds, ts + 2 * seconds
    ]
    assert len(merged) == 4
    assert len(changes) == 1
    assert added == [ts + 2 * seconds]


def test_three_rest_snapshots_must_be_semantically_identical():
    base = candle("1h", 1793170800, APPROVED["1h"][1793170800]["new"])
    second = deepcopy(base)
    third = deepcopy(base)
    third["close"] = "81088.5"

    with pytest.raises(ValueError, match="changed between"):
        validate_three_snapshots([[base], [second], [third]])


def test_three_rest_snapshots_ignore_textual_decimal_formatting_only():
    base = candle("1h", 1793170800, APPROVED["1h"][1793170800]["new"])
    second = deepcopy(base)
    third = deepcopy(base)
    second["volume"] = "110.3566380"
    third["quote_volume"] = "8935012.793541600"

    validate_three_snapshots([[base], [second], [third]])
