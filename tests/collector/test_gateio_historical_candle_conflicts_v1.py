from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.reconcile_gateio_historical_candle_conflicts_v1 import (
    APPROVED,
    reconcile_rows,
    resolve_runtime_root,
    validate_three_snapshots,
)


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


def approved_rows(timeframe: str, version: str) -> list[dict]:
    return [
        candle(timeframe, ts, item[version])
        for ts, item in sorted(APPROVED[timeframe].items())
    ]


def complete_approved_rows(timeframe: str, version: str) -> list[dict]:
    seconds = 3600 if timeframe == "1h" else 14400
    approved = APPROVED[timeframe]
    first, last = min(approved), max(approved)
    rows = []
    for ts in range(first, last + 1, seconds):
        values = approved[ts][version] if ts in approved else {
            "open": "100", "high": "102", "low": "99", "close": "101",
            "volume": "1", "quote_volume": "100",
        }
        rows.append(candle(timeframe, ts, values))
    return rows


def test_immutable_release_resolves_external_runtime_data_root(monkeypatch):
    monkeypatch.delenv("HES_GLOBAL_MARKET_DATA_ROOT", raising=False)
    release = Path("/opt/hes-trade-agent/releases/abc123")
    assert resolve_runtime_root(release) == Path("/opt/hes-trade-agent")


def test_explicit_runtime_data_root_override_is_respected(monkeypatch):
    monkeypatch.setenv("HES_GLOBAL_MARKET_DATA_ROOT", "/srv/hes-runtime")
    release = Path("/opt/hes-trade-agent/releases/abc123")
    assert resolve_runtime_root(release) == Path("/srv/hes-runtime")


@pytest.mark.parametrize("timeframe", ["1h", "4h"])
def test_only_pinned_historical_conflicts_can_be_reconciled(timeframe):
    old_rows = complete_approved_rows(timeframe, "old")
    rest_rows = complete_approved_rows(timeframe, "new")

    merged, changes, added = reconcile_rows(timeframe, old_rows, rest_rows)

    assert len(merged) == len(old_rows)
    assert len(changes) == len(APPROVED[timeframe])
    assert [row["open_time"] for row in merged] == [row["open_time"] for row in rest_rows]
    assert [row["close"] for row in merged] == [row["close"] for row in rest_rows]
    assert added == []


def test_reconciliation_ignores_decimal_formatting_only_differences():
    timeframe = "4h"
    old_rows = complete_approved_rows(timeframe, "old")
    rest_rows = complete_approved_rows(timeframe, "new")
    # The first non-conflict row has numerically identical values with a different scale.
    rest_rows[1]["volume"] = "1.000"

    merged, changes, added = reconcile_rows(timeframe, old_rows, rest_rows)

    assert len(merged) == len(old_rows)
    assert len(changes) == len(APPROVED[timeframe])
    assert added == []


def test_unapproved_historical_conflict_fails_closed():
    timeframe = "1h"
    old_rows = complete_approved_rows(timeframe, "old")
    rest_rows = complete_approved_rows(timeframe, "new")
    extra_ts = 1793170800 + 2 * 3600
    extra_old = candle(timeframe, extra_ts, {
        "open": "100", "high": "102", "low": "99", "close": "101",
        "volume": "1", "quote_volume": "100",
    })
    extra_changed = deepcopy(extra_old)
    extra_changed["close"] = "101.1"

    with pytest.raises(ValueError, match="Unapproved"):
        reconcile_rows(timeframe, old_rows + [extra_old], rest_rows + [extra_changed])


def test_reconciliation_rejects_identity_changes_even_for_pinned_numeric_rows():
    timeframe = "1h"
    old_rows = complete_approved_rows(timeframe, "old")
    rest_rows = complete_approved_rows(timeframe, "new")
    rest_rows[0]["close_time"] += 1

    with pytest.raises(ValueError, match="identity mismatch"):
        reconcile_rows(timeframe, old_rows, rest_rows)


def test_pinned_conflict_aborts_if_live_value_no_longer_matches_old_evidence():
    timeframe, open_time = "1h", 1793170800
    old_rows = complete_approved_rows(timeframe, "old")
    old_rows[0]["close"] = "81088.2"

    with pytest.raises(ValueError, match="neither pinned old nor corrected evidence"):
        reconcile_rows(timeframe, old_rows, complete_approved_rows(timeframe, "new"))


def test_pinned_conflict_aborts_if_rest_value_no_longer_matches_three_probe_evidence():
    timeframe = "1h"
    old_rows = complete_approved_rows(timeframe, "old")
    rest_rows = complete_approved_rows(timeframe, "new")
    rest_rows[0]["volume"] = "110.35663801"

    with pytest.raises(ValueError, match="pinned three-probe evidence"):
        reconcile_rows(timeframe, old_rows, rest_rows)


def test_reconciliation_aborts_if_any_pinned_conflict_identity_is_missing():
    timeframe = "1h"
    remaining = candle(timeframe, 1793174400, APPROVED[timeframe][1793174400]["old"])

    with pytest.raises(ValueError, match="pinned 1h conflict candle is missing"):
        reconcile_rows(
            timeframe,
            [remaining],
            [candle(timeframe, 1793174400, APPROVED[timeframe][1793174400]["new"])],
        )


def test_reconciliation_preserves_history_and_adds_new_closed_rows():
    timeframe = "1h"
    seconds = 3600
    ts = 1793170800
    before = candle(timeframe, ts - seconds, {
        "open": "100", "high": "102", "low": "99", "close": "101",
        "volume": "1", "quote_volume": "100",
    })
    existing_conflicts = complete_approved_rows(timeframe, "old")
    next_row = candle(timeframe, ts + 2 * seconds, {
        "open": "102", "high": "104", "low": "101", "close": "103",
        "volume": "3", "quote_volume": "300",
    })
    rest_rows = complete_approved_rows(timeframe, "new") + [deepcopy(next_row)]

    merged, changes, added = reconcile_rows(
        timeframe, [before] + existing_conflicts, rest_rows
    )

    assert [row["open_time"] for row in merged] == [
        ts - seconds, ts, ts + seconds, ts + 2 * seconds
    ]
    assert len(merged) == 4
    assert len(changes) == 2
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
