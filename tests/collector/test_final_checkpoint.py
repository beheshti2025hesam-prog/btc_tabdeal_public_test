import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tabdeal_futures_ws_test as collector


def _stub_startup(monkeypatch):
    # This test targets the final-checkpoint contract. Startup synchronization
    # is a separate safety boundary and must not race origin/main during this
    # unit test.
    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: None)


def test_main_raises_when_final_checkpoint_fails(monkeypatch):
    closed = {"value": False}

    _stub_startup(monkeypatch)
    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: None)
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    monkeypatch.setattr(collector, "git_checkpoint", lambda: False)

    def fake_close_csv():
        closed["value"] = True

    monkeypatch.setattr(collector, "close_csv", fake_close_csv)

    with pytest.raises(RuntimeError, match="Final Git checkpoint failed"):
        collector.main()

    assert closed["value"] is True


def test_main_completes_when_final_checkpoint_succeeds(monkeypatch):
    closed = {"value": False}

    _stub_startup(monkeypatch)
    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: None)
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    monkeypatch.setattr(collector, "git_checkpoint", lambda: True)

    def fake_close_csv():
        closed["value"] = True

    monkeypatch.setattr(collector, "close_csv", fake_close_csv)

    collector.main()

    assert closed["value"] is True


def test_push_checkpoint_targets_remote_main_from_detached_head(monkeypatch):
    commands = []

    monkeypatch.setattr(
        collector,
        "assert_remote_main_unchanged",
        lambda: "remote-main-sha",
    )
    monkeypatch.setattr(
        collector,
        "run_git",
        lambda command: commands.append(command),
    )

    assert collector.push_checkpoint(max_retries=1) is True

    assert commands == [[
        "git",
        "push",
        "origin",
        "HEAD:main",
    ]]
