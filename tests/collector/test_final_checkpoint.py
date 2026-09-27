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
