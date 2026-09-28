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


def test_checkpoint_updates_base_after_successful_push(monkeypatch, tmp_path):
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
    base_sha = ns["startup_base_sha"]

    write_csv(repo / "data/trades.csv", 100, 4)
    monkeypatch.chdir(repo)

    assert ns["git_checkpoint"]() is True
    assert ns["startup_base_sha"] != base_sha

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


def test_archive_rotation_preserves_all_rows(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write_csv(repo / "data/trades.csv", 100, 3)

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["MAX_ACTIVE_ROWS"] = 3
    ns["ARCHIVE_BATCH_ROWS"] = 2
    ns["active_rows"] = 3
    ns["csv_file"] = None
    ns["csv_writer"] = None
    monkeypatch.chdir(repo)

    assert ns["archive_old_rows"]() is True

    active = list(csv.DictReader((repo / "data/trades.csv").open(encoding="utf-8")))
    archives = list((repo / "data/archive").glob("*.csv"))
    assert len(archives) == 1
    archived = list(csv.DictReader(archives[0].open(encoding="utf-8")))

    all_sequences = [int(r["sequence"]) for r in archived + active]
    assert all_sequences == [100, 101, 102]
    assert [int(r["sequence"]) for r in archived] == [100, 101]
    assert [int(r["sequence"]) for r in active] == [102]


def test_plain_push_rejects_remote_advance_without_overwrite(monkeypatch, tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)

    first = tmp_path / "first"
    first.mkdir()
    git(first, "init", "-b", "main")
    git(first, "config", "user.email", "test@example.com")
    git(first, "config", "user.name", "test")
    write_csv(first / "data/trades.csv", 100, 3)
    git(first, "add", ".")
    git(first, "commit", "-m", "base")
    git(first, "remote", "add", "origin", str(origin))
    git(first, "push", "-u", "origin", "main")

    second = tmp_path / "second"
    subprocess.run(["git", "clone", str(origin), str(second)], check=True, capture_output=True)
    git(second, "config", "user.email", "second@example.com")
    git(second, "config", "user.name", "second")
    write_csv(second / "data/trades.csv", 100, 4)
    git(second, "add", "data/trades.csv")
    git(second, "commit", "-m", "newer checkpoint")
    git(second, "push", "origin", "main")

    # The stale first collector has no force-push path; normal git push must fail.
    write_csv(first / "data/trades.csv", 100, 3)
    git(first, "add", "data/trades.csv")
    git(first, "commit", "-m", "stale checkpoint")
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=first,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0

    verifier = tmp_path / "verifier"
    subprocess.run(["git", "clone", str(origin), str(verifier)], check=True, capture_output=True)
    rows = list(csv.DictReader((verifier / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102, 103]

def test_sequential_checkpoints_preserve_n_to_n_plus_2_chain(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    write_csv(repo / "data/trades.csv", 100, 3)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "N")
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-u", "origin", "main")

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["run_git"] = lambda command: subprocess.run(command, cwd=repo, check=True)

    # N -> N+1: append one valid trade and publish.
    ns["synchronize_startup_data_state"]()
    write_csv(repo / "data/trades.csv", 100, 4)
    assert ns["git_checkpoint"]() is True

    # N+1 -> N+2: a fresh collector session must start from persisted N+1,
    # then append another trade without losing predecessor rows.
    ns["synchronize_startup_data_state"]()
    rows = list(csv.DictReader((repo / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102, 103]

    write_csv(repo / "data/trades.csv", 100, 5)
    assert ns["git_checkpoint"]() is True

    verifier = tmp_path / "verifier"
    subprocess.run(["git", "clone", str(origin), str(verifier)], check=True, capture_output=True)
    persisted = list(csv.DictReader((verifier / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in persisted] == [100, 101, 102, 103, 104]
\n
def test_archive_rotation_never_reuses_existing_filename(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_csv(repo / "data/trades.csv", 100, 3)

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["MAX_ACTIVE_ROWS"] = 3
    ns["ARCHIVE_BATCH_ROWS"] = 2
    ns["active_rows"] = 3
    ns["csv_file"] = None
    ns["csv_writer"] = None
    monkeypatch.chdir(repo)

    import os
    import time
    os.makedirs(repo / "data/archive", exist_ok=True)
    fixed_time = 1759017600
    monkeypatch.setattr(ns["time"], "time", lambda: fixed_time)
    monkeypatch.setattr(ns["time"], "strftime", lambda *args: "20260928_000000")
    first = ns["archive_old_rows"]()
    assert first is True

    # Recreate a full active file and force the same second-resolution timestamp.
    write_csv(repo / "data/trades.csv", 200, 3)
    ns["active_rows"] = 3
    second = ns["archive_old_rows"]()
    assert second is True

    archives = sorted((repo / "data/archive").glob("*.csv"))
    assert len(archives) == 2
    rows = []
    for archive in archives:
        rows.extend(csv.DictReader(archive.open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 200, 201]
def test_archive_rotation_failure_does_not_leave_partial_temp_files(monkeypatch, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_csv(repo / "data/trades.csv", 100, 3)

    ns = load_namespace(monkeypatch, tmp_path)
    ns["OUTPUT_FILE"] = "data/trades.csv"
    ns["ARCHIVE_DIR"] = "data/archive"
    ns["MAX_ACTIVE_ROWS"] = 3
    ns["ARCHIVE_BATCH_ROWS"] = 2
    ns["active_rows"] = 3
    ns["csv_file"] = None
    ns["csv_writer"] = None
    monkeypatch.chdir(repo)

    real_replace = ns["os"].replace
    calls = {"count": 0}

    def fail_second_replace(src, dst):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected active-file replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(ns["os"], "replace", fail_second_replace)

    assert ns["archive_old_rows"]() is False
    assert not list((repo / "data/archive").glob("*.tmp"))
    assert not (repo / "data/trades.csv.tmp").exists()
    rows = list(csv.DictReader((repo / "data/trades.csv").open(encoding="utf-8")))
    assert [int(r["sequence"]) for r in rows] == [100, 101, 102]
    archives = list((repo / "data/archive").glob("*.csv"))
    assert archives == []
