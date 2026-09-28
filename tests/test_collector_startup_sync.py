import csv
import subprocess
from pathlib import Path

import pytest

COLLECTOR = Path(__file__).resolve().parents[1] / "tabdeal_futures_ws_test.py"

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)

def write_csv(path, start, count):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol","price","amount","side","updated","sequence"])
        for i in range(count):
            w.writerow(["BTC_USDT","1","1","buy","2026-09-28T00:00:00Z",start+i])

def load_namespace(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    ns = {"__name__":"collector_test_import"}
    source = COLLECTOR.read_text(encoding="utf-8")
    exec(compile(source, str(COLLECTOR), "exec"), ns)
    return ns

def test_startup_sync_replaces_stale_checkout(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write_csv(repo / "data/trades.csv", 100, 3)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")

    # Simulate a queued/stale checkout by changing only the working-tree data.
    write_csv(repo / "data/trades.csv", 1, 2)

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["run_git"] = lambda command: subprocess.run(command, cwd=repo, check=True)

    # A dirty data tree must fail closed rather than overwrite persisted data.
    with pytest.raises(RuntimeError):
        ns["synchronize_startup_data_state"]()

    # Remove the stale local modification, then verify the canonical remote state.
    git(repo, "restore", "--worktree", "--", "data/trades.csv")
    ns["synchronize_startup_data_state"]()
    rows = list(csv.DictReader((repo / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102]

def test_checkpoint_never_resets_worktree(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write_csv(repo / "data/trades.csv", 100, 3)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")

    # The checkpoint helper must stage the existing working tree, not replace it.
    write_csv(repo / "data/trades.csv", 100, 4)
    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["csv_file"] = None
    ns["run_git"] = lambda command: subprocess.run(command, cwd=repo, check=True)
    ns["prepare_git_checkpoint"]()
    rows = list(csv.DictReader((repo / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102, 103]


def test_checkpoint_fails_closed_when_main_advances(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write_csv(repo / "data/trades.csv", 100, 3)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "base")

    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", str(origin)],
        check=True,
        capture_output=True,
    )
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["run_git"] = lambda command: subprocess.run(
        command, cwd=repo, check=True
    )

    ns["synchronize_startup_data_state"]()

    # A second collector advances main after this collector's startup snapshot.
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", str(origin), str(other)],
        check=True,
        capture_output=True,
    )
    git(other, "config", "user.email", "other@example.com")
    git(other, "config", "user.name", "other")
    write_csv(other / "data/trades.csv", 100, 4)
    git(other, "add", "data/trades.csv")
    git(other, "commit", "-m", "concurrent checkpoint")
    git(other, "push", "origin", "main")

    # The first collector must refuse to publish from stale base SHA.
    with pytest.raises(RuntimeError, match="origin/main advanced"):
        ns["assert_remote_main_unchanged"]()

    # Verify the concurrent collector's newer persisted data remains intact.
    verifier = tmp_path / "verifier"
    subprocess.run(
        ["git", "clone", str(origin), str(verifier)],
        check=True,
        capture_output=True,
    )
    rows = list(
        csv.DictReader(
            (verifier / "data/trades.csv").open(encoding="utf-8")
        )
    )
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102, 103]
