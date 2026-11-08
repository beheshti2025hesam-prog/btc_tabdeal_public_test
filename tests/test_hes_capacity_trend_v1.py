import json
from pathlib import Path
from types import SimpleNamespace

from scripts.ops.hes_capacity_trend_v1 import collect_capacity_trend, inode_free_check


def usage(total, used):
    return SimpleNamespace(total=total, used=used, free=total-used)


def test_first_sample_creates_compact_baseline(tmp_path):
    state = tmp_path / "capacity.json"
    result = collect_capacity_trend(state_path=state, now=1000, usage_provider=lambda _: usage(1000, 500))
    assert result["state"] == "OK"
    assert result["sample_updated"] is True
    assert json.loads(state.read_text())["sample_count"] == 1


def test_sampling_is_hourly_not_every_five_minutes(tmp_path):
    state = tmp_path / "capacity.json"
    collect_capacity_trend(state_path=state, now=1000, usage_provider=lambda _: usage(1000, 500))
    result = collect_capacity_trend(state_path=state, now=1300, usage_provider=lambda _: usage(1000, 600))
    assert result["sample_updated"] is False
    assert result["sample_count"] == 1


def test_high_growth_forecast_becomes_critical_after_minimum_samples(tmp_path):
    state = tmp_path / "capacity.json"
    for i in range(6):
        result = collect_capacity_trend(
            state_path=state, now=1000+i*3600,
            usage_provider=lambda _, used=9000+i*100: usage(10000, used),
            min_samples=6,
        )
    assert result["state"] == "CRITICAL"
    assert result["time_to_full_hours"] < 24


def test_moderate_growth_forecast_warns(tmp_path):
    state = tmp_path / "capacity.json"
    for i in range(6):
        result = collect_capacity_trend(
            state_path=state, now=1000+i*3600,
            usage_provider=lambda _, used=4000+i*100: usage(10000, used),
            min_samples=6,
        )
    assert result["state"] == "WARN"
    assert 24 <= result["time_to_full_hours"] < 72


def test_corrupt_state_is_preserved_and_warned(tmp_path):
    state = tmp_path / "capacity.json"
    state.write_text("not-json")
    result = collect_capacity_trend(state_path=state, now=1000, usage_provider=lambda _: usage(1000, 500))
    assert result["state"] == "WARN"
    assert state.read_text() == "not-json"


def test_future_clock_does_not_overwrite_state(tmp_path):
    state = tmp_path / "capacity.json"
    collect_capacity_trend(state_path=state, now=1000, usage_provider=lambda _: usage(1000, 500))
    before = state.read_bytes()
    result = collect_capacity_trend(state_path=state, now=900, usage_provider=lambda _: usage(1000, 600))
    assert result["state"] == "WARN"
    assert state.read_bytes() == before


def test_filesystem_resize_resets_baseline(tmp_path):
    state = tmp_path / "capacity.json"
    collect_capacity_trend(state_path=state, now=1000, usage_provider=lambda _: usage(1000, 500))
    result = collect_capacity_trend(state_path=state, now=5000, usage_provider=lambda _: usage(2000, 1000))
    assert result["detail"].startswith("filesystem_size_changed")
    assert json.loads(state.read_text())["sample_count"] == 1


def test_inode_free_check_ok_warn_and_critical():
    ok = inode_free_check(statvfs_provider=lambda _: SimpleNamespace(f_files=1000, f_favail=870))
    warn = inode_free_check(statvfs_provider=lambda _: SimpleNamespace(f_files=1000, f_favail=80))
    critical = inode_free_check(statvfs_provider=lambda _: SimpleNamespace(f_files=1000, f_favail=40))
    assert ok[0] == "OK"
    assert warn[0] == "WARN"
    assert critical[0] == "CRITICAL"


def test_inode_zero_total_fails_closed():
    result = inode_free_check(statvfs_provider=lambda _: SimpleNamespace(f_files=0, f_favail=0))
    assert result == ("CRITICAL", "inode_metrics_invalid")
