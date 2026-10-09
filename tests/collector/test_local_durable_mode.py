import csv
import json
from pathlib import Path

import pytest

import tabdeal_futures_ws_test as collector


def write_trade_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "price", "amount", "side", "updated", "sequence"])
        writer.writerows(rows)


def test_local_durable_mode_skips_git_sync_and_publication(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    write_trade_csv(
        tmp_path / "data/trades.csv",
        [["BTC_USDT", "100", "0.1", "Buy", "2026-10-09T00:00:00+00:00", "100"]],
    )
    monkeypatch.setattr(collector, "LOCAL_DURABLE_MODE", True)
    monkeypatch.setattr(
        collector, "synchronize_startup_data_state",
        lambda: pytest.fail("local durable mode must not fetch or restore Git state"),
    )
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    monkeypatch.setattr(collector, "flush_csv", lambda: None)
    monkeypatch.setattr(collector, "close_csv", lambda: None)
    monkeypatch.setattr(
        collector, "git_checkpoint",
        lambda: pytest.fail("local durable mode must not publish to Git"),
    )

    collector.main()

    assert (tmp_path / "data/trades.csv").exists()
    heartbeat = tmp_path / "data/forward/collector_heartbeat_v1.json"
    record = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert record["status"] == "STOPPED"
    assert record["writer_lock_held"] is False


def test_local_durable_mode_fails_closed_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(collector, "LOCAL_DURABLE_MODE", True)
    monkeypatch.setattr(collector, "acquire_single_writer_lock", lambda: None)
    monkeypatch.setattr(collector, "release_single_writer_lock", lambda: None)
    monkeypatch.setattr(
        collector, "open_csv",
        lambda: pytest.fail("must validate local evidence before opening writer"),
    )

    with pytest.raises(RuntimeError, match="existing data/trades.csv"):
        collector.main()


@pytest.mark.parametrize("rows", [[], [["BTC_USDT", "100", "0.1", "Buy", "bad-time", "100"]]])
def test_local_durable_mode_rejects_empty_or_invalid_evidence(monkeypatch, tmp_path, rows):
    monkeypatch.chdir(tmp_path)
    write_trade_csv(tmp_path / "data/trades.csv", rows)
    monkeypatch.setattr(collector, "LOCAL_DURABLE_MODE", True)
    monkeypatch.setattr(collector, "acquire_single_writer_lock", lambda: None)
    monkeypatch.setattr(collector, "release_single_writer_lock", lambda: None)

    with pytest.raises(RuntimeError):
        collector.main()
