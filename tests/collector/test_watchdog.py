import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import scripts.collector_watchdog as watchdog


def write_trades(path: Path, updated: str, sequence: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "price", "amount", "side", "updated", "sequence"])
        writer.writerow(["BTC_USDT", "100", "1", "buy", updated, sequence])


def test_watchdog_accepts_fresh_trade(monkeypatch, tmp_path):
    trades = tmp_path / "data" / "trades.csv"
    updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_trades(trades, updated)

    monkeypatch.setattr(watchdog, "TRADES", trades)
    monkeypatch.setattr(watchdog, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(watchdog, "MAX_TRADE_AGE", 180)

    assert watchdog.main() == 0


def test_watchdog_rejects_stale_trade(monkeypatch, tmp_path):
    trades = tmp_path / "data" / "trades.csv"
    stale = datetime.fromtimestamp(time.time() - 600, timezone.utc).isoformat().replace("+00:00", "Z")
    write_trades(trades, stale)

    monkeypatch.setattr(watchdog, "TRADES", trades)
    monkeypatch.setattr(watchdog, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(watchdog, "MAX_TRADE_AGE", 180)

    assert watchdog.main() == 1


def test_watchdog_parses_epoch_milliseconds():
    assert watchdog.parse_timestamp("1779700000000") == 1779700000.0


def test_watchdog_parses_iso_timestamp():
    assert watchdog.parse_timestamp("2026-09-28T05:00:00Z") == 1790571600.0


def test_watchdog_rejects_dead_supervisor(monkeypatch, tmp_path):
    trades = tmp_path / "data" / "trades.csv"
    updated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_trades(trades, updated)

    monkeypatch.setattr(watchdog, "TRADES", trades)
    monkeypatch.setattr(watchdog, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(watchdog, "MAX_TRADE_AGE", 180)
    monkeypatch.setattr(
        watchdog.os,
        "kill",
        lambda pid, signal: (_ for _ in ()).throw(ProcessLookupError(pid)),
    )
    watchdog.STATE.write_text(
        '{"event":"collector_started","pid":999999}',
        encoding="utf-8",
    )

    assert watchdog.main() == 1
