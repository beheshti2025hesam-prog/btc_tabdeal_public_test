import os
import subprocess
import sys


def test_persistent_mode_disables_git_checkpoint_at_import(tmp_path):
    code = """
import tabdeal_futures_ws_test as collector
print(collector.PERSISTENT_MODE)
print(collector.RUN_SECONDS)
print(collector.GIT_CHECKPOINT_ENABLED)
"""
    env = os.environ.copy()
    env["HES_COLLECTOR_MODE"] = "persistent-vps"
    env["HES_COLLECTOR_GIT_CHECKPOINT"] = "0"

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=tmp_path.parent.parent,
        env=env,
        check=True,
    )

    lines = result.stdout.strip().splitlines()
    assert lines == ["True", "None", "False"]


def test_default_mode_keeps_finite_runtime_and_git_checkpoint_enabled(tmp_path):
    code = """
import tabdeal_futures_ws_test as collector
print(collector.PERSISTENT_MODE)
print(collector.RUN_SECONDS)
print(collector.GIT_CHECKPOINT_ENABLED)
"""
    env = os.environ.copy()
    env.pop("HES_COLLECTOR_MODE", None)
    env.pop("HES_COLLECTOR_GIT_CHECKPOINT", None)

    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=tmp_path.parent.parent,
        env=env,
        check=True,
    )

    lines = result.stdout.strip().splitlines()
    assert lines == ["False", "19200", "True"]
