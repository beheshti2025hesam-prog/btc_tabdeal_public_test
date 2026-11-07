import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tabdeal_futures_ws_test as collector


def test_main_raises_when_final_checkpoint_fails(monkeypatch, tmp_path):
    closed = {"value": False}

    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: None)
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    # main() normally synchronizes the collector checkout and may move its
    # Git index/HEAD. This unit test is only about final-checkpoint behavior;
    # isolate it from every real repository mutation.
    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: None)
    monkeypatch.setattr(collector, "git_checkpoint", lambda: False)
    monkeypatch.setattr(collector, "SINGLE_WRITER_LOCK_FILE", str(tmp_path / ".collector.lock"))

    def fake_close_csv():
        closed["value"] = True

    monkeypatch.setattr(collector, "close_csv", fake_close_csv)

    with pytest.raises(RuntimeError, match="Final Git checkpoint failed"):
        collector.main()

    assert closed["value"] is True


def test_main_completes_when_final_checkpoint_succeeds(monkeypatch, tmp_path):
    closed = {"value": False}

    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: None)
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    # Never let this isolated unit test synchronize or reset its caller's Git tree.
    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: None)
    monkeypatch.setattr(collector, "git_checkpoint", lambda: True)
    monkeypatch.setattr(collector, "SINGLE_WRITER_LOCK_FILE", str(tmp_path / ".collector.lock"))

    def fake_close_csv():
        closed["value"] = True

    monkeypatch.setattr(collector, "close_csv", fake_close_csv)

    collector.main()

    assert closed["value"] is True
