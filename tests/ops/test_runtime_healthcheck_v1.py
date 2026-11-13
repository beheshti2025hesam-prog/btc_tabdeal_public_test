from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import scripts.ops.hes_runtime_healthcheck_v1 as health


class FakeRunner:
    def __init__(self, inactive=()):
        self.inactive = set(inactive)
        self.commands = []

    def __call__(self, args, **kwargs):
        self.commands.append(tuple(args))
        unit = args[-1]
        return subprocess.CompletedProcess(args, 3 if unit in self.inactive else 0, '', '')


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')


def test_runtime_healthcheck_includes_precision_journal_service():
    runner = FakeRunner()
    report = health.collect_checks(root=Path('/tmp/not-used'), now=1_800_000_000, runner=runner)
    names = {row['check'] for row in report['checks']}
    assert 'service:hes-precision-entry-journal.service' in names
    assert all(args[1] != 'start' and args[1] != 'restart' for args in runner.commands)


def test_runtime_healthcheck_validates_precision_paper_only_and_daily_cap(tmp_path, monkeypatch):
    # This test isolates precision/paper-only invariants; disk thresholds have
    # separate production checks and must not depend on the VPS filesystem.
    monkeypatch.setattr(health.shutil, "disk_usage", lambda _path: SimpleNamespace(total=100, used=50, free=50))
    now = 2_000_000_000
    data = tmp_path / 'data' / 'forward'
    data.mkdir(parents=True)
    for filename in health.FRESHNESS_LIMITS:
        path = data / filename
        if filename.endswith('.jsonl'):
            _write_jsonl(path, [{'observed_at': _iso(now), 'event_id': filename, 'execution_enabled': False, 'orders_placed': False}])
        else:
            path.write_text(json.dumps({'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False, 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT'}), encoding='utf-8')
    (data / 'precision_entry_journal_report_v1.json').write_text(json.dumps({
        'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False,
        'event_count': 0, 'candidate_count': 0, 'outcome_count': 0,
        'daily_signal_cap': 3, 'daily_signal_cap_is_quota': False,
    }), encoding='utf-8')
    for filename in ('precision_entry_events_v1.jsonl', 'precision_entry_candidates_v1.jsonl', 'precision_entry_outcomes_v1.jsonl'):
        (data / filename).unlink(missing_ok=True)
    witness = tmp_path / 'witness.jsonl'
    _write_jsonl(witness, [{'observed_at': _iso(now), 'status': 'PASS', 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT', 'timeframe': '1m', 'execution_enabled': False, 'orders_placed': False, 'latest_age_seconds': 20}])
    monkeypatch.setattr(health, 'WITNESS', witness)
    # Keep the healthcheck unit test independent of the host running pytest.
    monkeypatch.setattr(health.shutil, 'disk_usage', lambda _: health.shutil._ntuple_diskusage(100, 50, 50))
    runner = FakeRunner()
    report = health.collect_checks(root=tmp_path, now=now, runner=runner)
    assert report['overall'] == 'OK'
    before = {p.relative_to(tmp_path): hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    health.collect_checks(root=tmp_path, now=now, runner=runner)
    after = {p.relative_to(tmp_path): hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    assert before == after
    assert all(args[1] != 'start' and args[1] != 'restart' for args in runner.commands)


def test_runtime_healthcheck_flags_unsafe_precision_event(tmp_path, monkeypatch):
    now = 2_000_000_000
    data = tmp_path / 'data' / 'forward'
    data.mkdir(parents=True)
    for filename in health.FRESHNESS_LIMITS:
        path = data / filename
        if filename.endswith('.jsonl'):
            _write_jsonl(path, [{'observed_at': _iso(now), 'event_id': filename, 'execution_enabled': False, 'orders_placed': False}])
        else:
            path.write_text(json.dumps({'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False, 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT'}), encoding='utf-8')
    report_path = data / 'precision_entry_journal_report_v1.json'
    report_path.write_text(json.dumps({'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False,
        'event_count': 1, 'candidate_count': 0, 'outcome_count': 0, 'daily_signal_cap': 3, 'daily_signal_cap_is_quota': False}), encoding='utf-8')
    _write_jsonl(data / 'precision_entry_events_v1.jsonl', [{'event_id': 'bad', 'observed_at': _iso(now), 'source': 'tabdeal', 'symbol': 'BTC_USDT', 'timeframe': '1m', 'execution_enabled': True, 'orders_placed': False}])
    (data / 'precision_entry_candidates_v1.jsonl').unlink(missing_ok=True)
    (data / 'precision_entry_outcomes_v1.jsonl').unlink(missing_ok=True)
    witness = tmp_path / 'witness.jsonl'
    _write_jsonl(witness, [{'observed_at': _iso(now), 'status': 'PASS', 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT', 'timeframe': '1m', 'execution_enabled': False, 'orders_placed': False, 'latest_age_seconds': 20}])
    monkeypatch.setattr(health, 'WITNESS', witness)
    report = health.collect_checks(root=tmp_path, now=now, runner=FakeRunner())
    assert report['overall'] == 'CRITICAL'
    names = {issue['check'] for issue in report['issues']}
    assert 'precision:precision_entry_events_v1.jsonl:paper_only' in names
    assert 'precision:precision_entry_events_v1.jsonl:source_identity' in names


def test_runtime_healthcheck_blocks_more_than_three_candidates_per_utc_day(tmp_path, monkeypatch):
    now = 2_000_000_000
    data = tmp_path / 'data' / 'forward'
    data.mkdir(parents=True)
    for filename in health.FRESHNESS_LIMITS:
        path = data / filename
        if filename.endswith('.jsonl'):
            _write_jsonl(path, [{'observed_at': _iso(now), 'event_id': filename, 'execution_enabled': False, 'orders_placed': False}])
        else:
            path.write_text(json.dumps({'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False, 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT'}), encoding='utf-8')
    candidates = []
    for index in range(4):
        candidates.append({
            'event_id': f'c{index}', 'candidate_event_id': f'c{index}', 'entry_time': now - index,
            'source': 'gateio_public_spot', 'symbol': 'BTC_USDT', 'timeframe': '1m',
            'execution_enabled': False, 'orders_placed': False,
        })
    _write_jsonl(data / 'precision_entry_candidates_v1.jsonl', candidates)
    (data / 'precision_entry_journal_report_v1.json').write_text(json.dumps({
        'updated_at': _iso(now), 'execution_enabled': False, 'orders_placed': False,
        'event_count': 0, 'candidate_count': 4, 'outcome_count': 0,
        'daily_signal_cap': 3, 'daily_signal_cap_is_quota': False,
    }), encoding='utf-8')
    (data / 'precision_entry_events_v1.jsonl').unlink(missing_ok=True)
    (data / 'precision_entry_outcomes_v1.jsonl').unlink(missing_ok=True)
    witness = tmp_path / 'witness.jsonl'
    _write_jsonl(witness, [{'observed_at': _iso(now), 'status': 'PASS', 'source': 'gateio_public_spot', 'symbol': 'BTC_USDT', 'timeframe': '1m', 'execution_enabled': False, 'orders_placed': False, 'latest_age_seconds': 20}])
    monkeypatch.setattr(health, 'WITNESS', witness)
    report = health.collect_checks(root=tmp_path, now=now, runner=FakeRunner())
    assert report['overall'] == 'CRITICAL'
    assert any(issue['check'] == 'precision:daily_signal_cap' for issue in report['issues'])



def test_runtime_healthcheck_warns_when_disk_free_is_below_fifteen_percent(tmp_path, monkeypatch):
    monkeypatch.setattr(health.shutil, 'disk_usage', lambda _: health.shutil._ntuple_diskusage(100, 87, 13))
    report = health.collect_checks(root=tmp_path, now=2_000_000_000, runner=FakeRunner())
    disk_check = next(row for row in report['checks'] if row['check'] == 'disk-free')
    assert disk_check['state'] == 'WARN'
    assert disk_check['detail'] == '13.0%'