import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tabdeal_futures_ws_test as collector


def _write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "price", "amount", "side", "updated", "sequence"])
        writer.writerows(rows)


def _read_sequences(path):
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [int(row["sequence"]) for row in reader]


def test_archive_rotation_recovery_after_archive_replace_failure(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    output = data_dir / "trades.csv"

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(collector, "ROTATION_MARKER", str(archive_dir / ".archive_rotation.json"))
    monkeypatch.setattr(collector, "MAX_ACTIVE_ROWS", 5)
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 2)
    monkeypatch.setattr(collector, "active_rows", 5)
    monkeypatch.setattr(collector, "csv_file", None)
    monkeypatch.setattr(collector, "csv_writer", None)

    rows = [
        ["BTC_USDT", "100", "1", "buy", "2026-09-27T00:00:00Z", str(seq)]
        for seq in range(1, 6)
    ]
    _write_rows(output, rows)

    real_replace = collector.os.replace
    replace_calls = {"count": 0}

    def fail_on_active_replace(src, dst):
        replace_calls["count"] += 1
        if replace_calls["count"] == 3:
            raise OSError("simulated crash at active replacement")
        return real_replace(src, dst)

    monkeypatch.setattr(collector.os, "replace", fail_on_active_replace)

    assert collector.archive_old_rows() is False
    assert output.exists()
    assert os.path.exists(collector.ROTATION_MARKER)

    monkeypatch.setattr(collector.os, "replace", real_replace)
    collector.recover_archive_rotation()

    archives = list(archive_dir.glob("trades_archive_*.csv"))
    assert len(archives) == 1
    assert _read_sequences(archives[0]) == [1, 2]
    assert _read_sequences(output) == [3, 4, 5]
    assert not os.path.exists(collector.ROTATION_MARKER)
    assert not os.path.exists(str(output) + ".rotation-backup")


def test_archive_rotation_recovery_rolls_back_before_archive_commit(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    output = data_dir / "trades.csv"
    archive_dir.mkdir(parents=True)

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(collector, "ROTATION_MARKER", str(archive_dir / ".archive_rotation.json"))
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 2)

    rows = [
        ["BTC_USDT", "100", "1", "buy", "2026-09-27T00:00:00Z", str(seq)]
        for seq in range(1, 6)
    ]
    backup = Path(str(output) + ".rotation-backup")
    _write_rows(backup, rows)

    marker = {
        "archive_file": str(archive_dir / "trades_archive_20260927_000000.csv"),
        "temp_archive": str(archive_dir / "trades_archive_20260927_000000.csv.tmp"),
        "temp_active": str(output) + ".tmp",
        "backup_active": str(backup),
    }
    with open(collector.ROTATION_MARKER, "w", encoding="utf-8") as handle:
        json.dump(marker, handle)

    collector.recover_archive_rotation()

    assert _read_sequences(output) == [1, 2, 3, 4, 5]
    assert not backup.exists()
    assert not os.path.exists(collector.ROTATION_MARKER)
    assert not list(archive_dir.glob("trades_archive_*.csv"))


def test_main_recovers_archive_rotation_before_startup_sync(monkeypatch):
    order = []

    monkeypatch.setattr(collector, "recover_archive_rotation", lambda: order.append("recover"))
    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: order.append("sync"))
    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: order.append("sequence") or None)
    monkeypatch.setattr(collector, "open_csv", lambda: order.append("open"))
    monkeypatch.setattr(collector, "collect", lambda: order.append("collect"))
    monkeypatch.setattr(collector, "git_checkpoint", lambda: order.append("checkpoint") or True)
    monkeypatch.setattr(collector, "close_csv", lambda: order.append("close"))

    collector.main()

    assert order[:3] == ["recover", "sync", "sequence"]


def test_archive_rotation_preserves_sequence_boundary(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    output = data_dir / "trades.csv"

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(
        collector,
        "ROTATION_MARKER",
        str(archive_dir / ".archive_rotation.json"),
    )
    monkeypatch.setattr(collector, "MAX_ACTIVE_ROWS", 5)
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 2)
    monkeypatch.setattr(collector, "active_rows", 5)
    monkeypatch.setattr(collector, "csv_file", None)
    monkeypatch.setattr(collector, "csv_writer", None)

    rows = [
        ["BTC_USDT", "100", "1", "buy", f"2026-09-27T00:00:0{seq}Z", str(seq)]
        for seq in range(1, 6)
    ]
    _write_rows(output, rows)

    assert collector.archive_old_rows() is True

    archives = list(archive_dir.glob("trades_archive_*.csv"))
    assert len(archives) == 1
    assert _read_sequences(archives[0]) == [1, 2]
    assert _read_sequences(output) == [3, 4, 5]
    assert _read_sequences(archives[0])[-1] < _read_sequences(output)[0]
    assert collector.active_rows == 3


def test_archive_rotation_refuses_existing_archive_target(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    output = data_dir / "trades.csv"

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(
        collector,
        "ROTATION_MARKER",
        str(archive_dir / ".archive_rotation.json"),
    )
    monkeypatch.setattr(collector, "MAX_ACTIVE_ROWS", 5)
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 2)
    monkeypatch.setattr(collector, "active_rows", 5)
    monkeypatch.setattr(collector, "csv_file", None)
    monkeypatch.setattr(collector, "csv_writer", None)

    rows = [
        ["BTC_USDT", "100", "1", "buy", "2026-09-27T00:00:00Z", str(seq)]
        for seq in range(1, 6)
    ]
    _write_rows(output, rows)
    archive_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(collector.time, "strftime", lambda *args, **kwargs: "20260927_000000")
    existing = archive_dir / "trades_archive_20260927_000000.csv"
    _write_rows(existing, [["BTC_USDT", "99", "1", "buy", "2026-09-26T23:59:59Z", "0"]])

    assert collector.archive_old_rows() is False
    assert _read_sequences(output) == [1, 2, 3, 4, 5]
    assert _read_sequences(existing) == [0]


def test_archive_rotation_preserves_timestamp_sequence_order(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    archive_dir = data_dir / "archive"
    output = data_dir / "trades.csv"

    monkeypatch.setattr(collector, "OUTPUT_FILE", str(output))
    monkeypatch.setattr(collector, "ARCHIVE_DIR", str(archive_dir))
    monkeypatch.setattr(
        collector, "ROTATION_MARKER", str(archive_dir / ".archive_rotation.json")
    )
    monkeypatch.setattr(collector, "MAX_ACTIVE_ROWS", 5)
    monkeypatch.setattr(collector, "ARCHIVE_BATCH_ROWS", 2)
    monkeypatch.setattr(collector, "active_rows", 5)
    monkeypatch.setattr(collector, "csv_file", None)
    monkeypatch.setattr(collector, "csv_writer", None)

    rows = [
        ["BTC_USDT", "100", "1", "buy", "2026-09-27T00:00:01Z", "10"],
        ["BTC_USDT", "101", "1", "buy", "2026-09-27T00:00:02Z", "11"],
        ["BTC_USDT", "102", "1", "buy", "2026-09-27T00:00:03Z", "12"],
        ["BTC_USDT", "103", "1", "buy", "2026-09-27T00:00:04Z", "13"],
        ["BTC_USDT", "104", "1", "buy", "2026-09-27T00:00:05Z", "14"],
    ]
    _write_rows(output, rows)

    assert collector.archive_old_rows() is True
    archives = list(archive_dir.glob("trades_archive_*.csv"))
    assert len(archives) == 1

    archived = _read_sequences(archives[0])
    active = _read_sequences(output)
    assert archived == [10, 11]
    assert active == [12, 13, 14]
    assert max(archived) < min(active)
