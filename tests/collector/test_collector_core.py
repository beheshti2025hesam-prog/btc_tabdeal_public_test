import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tabdeal_futures_ws_test as collector


def test_runtime_override(monkeypatch):
    monkeypatch.setenv("COLLECTOR_RUN_SECONDS", "16200")
    assert collector.get_run_seconds() == 16200


def test_runtime_rejects_invalid_values(monkeypatch):
    for value in ("0", "-1", "abc", "1.5"):
        monkeypatch.setenv("COLLECTOR_RUN_SECONDS", value)
        with pytest.raises(ValueError):
            collector.get_run_seconds()


def test_global_max_sequence_uses_active_and_archives(tmp_path, monkeypatch):
    active = tmp_path / "trades.csv"
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    header = ["symbol", "price", "amount", "side", "updated", "sequence"]

    with active.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(["BTC_USDT", "1", "1", "buy", "1", "100"])
        w.writerow(["BTC_USDT", "1", "1", "buy", "2", "90"])

    with (archive_dir / "trades_archive_test.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerow(["BTC_USDT", "1", "1", "buy", "0", "250"])

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(active))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))

    assert collector.load_global_last_sequence() == 250


def test_save_trade_rejects_duplicate_and_backward_sequence(tmp_path, monkeypatch):
    output = tmp_path / "trades.csv"
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(collector, "last_sequence", 99)
    monkeypatch.setattr(collector, "trade_count", 0)
    monkeypatch.setattr(collector, "active_rows", 0)

    collector.csv_file = output.open("a", newline="", encoding="utf-8")
    collector.csv_writer = csv.writer(collector.csv_file)
    collector.csv_writer.writerow(
        ["symbol", "price", "amount", "side", "updated", "sequence"]
    )

    collector.save_trade(
        {
            "symbol": "BTC_USDT",
            "price": "1",
            "amount": "1",
            "side_name": "buy",
            "updated": "1",
            "sequence": 100,
        }
    )
    collector.save_trade(
        {
            "symbol": "BTC_USDT",
            "price": "1",
            "amount": "1",
            "side_name": "buy",
            "updated": "2",
            "sequence": 99,
        }
    )

    collector.csv_file.close()
    collector.csv_file = None
    collector.csv_writer = None

    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["sequence"] == "100"


def test_archive_moves_exact_batch_and_preserves_newest_rows(tmp_path, monkeypatch):
    output = tmp_path / "trades.csv"
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()

    header = ["symbol", "price", "amount", "side", "updated", "sequence"]
    with output.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for seq in range(1, 11):
            w.writerow(["BTC_USDT", str(seq), "1", "buy", str(seq), seq])

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(collector, "MAX_ACTIVE_ROWS", 10)
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 4)
    monkeypatch.setattr(collector, "active_rows", 10)

    collector.csv_file = None
    collector.csv_writer = None

    assert collector.archive_old_rows() is True
    assert collector.active_rows == 6

    archives = list(archive_dir.glob("*.csv"))
    assert len(archives) == 1

    archived = list(csv.DictReader(archives[0].open(encoding="utf-8")))
    active = list(csv.DictReader(output.open(encoding="utf-8")))

    assert [int(r["sequence"]) for r in archived] == [1, 2, 3, 4]
    assert [int(r["sequence"]) for r in active] == [5, 6, 7, 8, 9, 10]

    collector.close_csv()
