"""Regression contract for the 24/7 Tabdeal collector schedule.

This test validates the intended scheduler/collector safety configuration.
It does not claim that GitHub Actions actually started every scheduled run;
runtime continuity still requires execution-history evidence.
"""

from pathlib import Path
import re


WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "run.yml"


def _workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def test_collector_schedule_has_six_four_hour_starts():
    text = _workflow_text()
    crons = re.findall(r'- cron: "([^"]+)"', text)
    assert crons == [
        "15 00 * * *",
        "15 04 * * *",
        "15 08 * * *",
        "15 12 * * *",
        "15 16 * * *",
        "15 20 * * *",
    ]


def test_runtime_exceeds_cadence_with_explicit_overlap():
    text = _workflow_text()
    match = re.search(r'COLLECTOR_RUN_SECONDS:\s*"([0-9]+)"', text)
    assert match
    runtime = int(match.group(1))
    cadence = 4 * 60 * 60
    assert runtime == 5 * 60 * 60 + 20 * 60
    assert runtime > cadence
    assert runtime - cadence == 80 * 60


def test_collector_concurrency_is_fail_safe_for_shared_csv():
    text = _workflow_text()
    assert "group: tabdeal-btc-usdt-collector" in text
    assert "cancel-in-progress: false" in text
    assert "queue: max" in text


def test_runner_timeout_leaves_shutdown_margin():
    text = _workflow_text()
    match = re.search(r'timeout-minutes:\s*([0-9]+)', text)
    assert match
    timeout_minutes = int(match.group(1))
    assert timeout_minutes == 350
    assert timeout_minutes * 60 - (5 * 60 * 60 + 20 * 60) == 30 * 60
