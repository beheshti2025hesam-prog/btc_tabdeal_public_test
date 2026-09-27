import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tabdeal_futures_ws_test as collector


def test_startup_sync_refreshes_clean_stale_checkout(monkeypatch):
    commands = []

    def fake_run_git(command):
        commands.append(command)

    class Result:
        def __init__(self, stdout="", returncode=0):
            self.stdout = stdout
            self.returncode = returncode

    def fake_subprocess_run(command, **kwargs):
        if command[:2] == ["git", "status"]:
            return Result(stdout="")
        if command[:2] == ["git", "diff"]:
            return Result(returncode=0)
        raise AssertionError(command)

    monkeypatch.setattr(collector, "run_git", fake_run_git)
    monkeypatch.setattr(collector.subprocess, "run", fake_subprocess_run)

    collector.synchronize_startup_data_state()

    assert ["git", "fetch", "origin", "main"] in commands
    assert [
        "git", "restore", "--source=origin/main", "--worktree",
        "--", collector.OUTPUT_FILE, collector.ARCHIVE_DIR
    ] in commands


def test_startup_sync_refuses_dirty_local_data(monkeypatch):
    commands = []

    def fake_run_git(command):
        commands.append(command)

    class Result:
        stdout = " M data/trades.csv\\n"
        returncode = 0

    monkeypatch.setattr(collector, "run_git", fake_run_git)
    monkeypatch.setattr(collector.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="local collector data modifications"):
        collector.synchronize_startup_data_state()

    assert ["git", "fetch", "origin", "main"] in commands
    assert not any(command[:2] == ["git", "restore"] for command in commands)


def test_main_raises_when_final_checkpoint_fails(monkeypatch):
    closed = {"value": False}

    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: None)

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

    monkeypatch.setattr(collector, "synchronize_startup_data_state", lambda: None)

    monkeypatch.setattr(collector, "load_global_last_sequence", lambda: None)
    monkeypatch.setattr(collector, "open_csv", lambda: None)
    monkeypatch.setattr(collector, "collect", lambda: None)
    monkeypatch.setattr(collector, "git_checkpoint", lambda: True)

    def fake_close_csv():
        closed["value"] = True

    monkeypatch.setattr(collector, "close_csv", fake_close_csv)

    collector.main()

    assert closed["value"] is True


def test_main_syncs_before_sequence_recovery_and_csv_open(monkeypatch):
    order = []

    monkeypatch.setattr(
        collector,
        "synchronize_startup_data_state",
        lambda: order.append("sync"),
    )
    monkeypatch.setattr(
        collector,
        "load_global_last_sequence",
        lambda: order.append("sequence") or None,
    )
    monkeypatch.setattr(
        collector,
        "open_csv",
        lambda: order.append("open"),
    )
    monkeypatch.setattr(
        collector,
        "collect",
        lambda: order.append("collect"),
    )
    monkeypatch.setattr(
        collector,
        "git_checkpoint",
        lambda: order.append("checkpoint") or True,
    )
    monkeypatch.setattr(
        collector,
        "close_csv",
        lambda: order.append("close"),
    )

    collector.main()

    assert order[:3] == ["sync", "sequence", "open"]


def test_startup_sync_refuses_dirty_archive(monkeypatch):
    commands = []

    def fake_run_git(command):
        commands.append(command)

    class Result:
        stdout = " M data/archive/trades_20260927.csv\\n"
        returncode = 0

    monkeypatch.setattr(collector, "run_git", fake_run_git)
    monkeypatch.setattr(collector.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="local collector data modifications"):
        collector.synchronize_startup_data_state()

    assert not any(command[:2] == ["git", "restore"] for command in commands)


def test_push_checkpoint_does_not_reset_and_restage_after_remote_advance(monkeypatch):
    commands = []
    attempts = {"push": 0}

    def fake_run_git(command):
        commands.append(command)
        if command[:2] == ["git", "push"]:
            attempts["push"] += 1
            raise RuntimeError("non-fast-forward")

    monkeypatch.setattr(collector, "run_git", fake_run_git)

    assert collector.push_checkpoint(max_retries=3) is False
    assert attempts["push"] == 1
    assert ["git", "fetch", "origin", "main"] in commands
    assert not any(command[:3] == ["git", "reset", "--mixed"] for command in commands)
    assert not any(command[:2] == ["git", "add"] for command in commands)


def test_prepare_checkpoint_does_not_mixed_reset_after_startup_alignment(monkeypatch):
    commands = []

    monkeypatch.setattr(collector, "flush_csv", lambda: None)

    def fake_run_git(command):
        commands.append(command)

    monkeypatch.setattr(collector, "run_git", fake_run_git)
    monkeypatch.setattr(collector, "subprocess", collector.subprocess)

    collector.prepare_git_checkpoint()

    assert ["git", "fetch", "origin", "main"] in commands
    assert ["git", "add", collector.OUTPUT_FILE, collector.ARCHIVE_DIR] in commands
    assert not any(command[:3] == ["git", "reset", "--mixed"] for command in commands)
