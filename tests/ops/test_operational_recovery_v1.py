from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from scripts.ops.hes_operational_recovery_v1 import (
    DEPENDENCIES,
    REPAIR_ORDER,
    OperationalRecoveryV1,
    deployment_lock_held,
    verify_active_release,
)


class FakeSystemd:
    def __init__(self, active=(), enabled=(), fail_start=()):
        self.active = set(active)
        self.enabled = set(enabled) | set(REPAIR_ORDER)
        self.fail_start = set(fail_start)
        self.commands = []

    def __call__(self, args, **kwargs):
        self.commands.append(tuple(args))
        if args[:2] == ['systemctl', 'is-active']:
            return subprocess.CompletedProcess(args, 0 if args[-1] in self.active else 3, '', '')
        if args[:2] == ['systemctl', 'is-enabled']:
            return subprocess.CompletedProcess(args, 0 if args[-1] in self.enabled else 1, '', '')
        if args[:2] == ['systemctl', 'show']:
            return subprocess.CompletedProcess(args, 0, 'active' if args[-1] in self.active else 'inactive', '')
        if args[:2] == ['systemctl', 'start']:
            unit = args[-1]
            if unit in self.fail_start:
                return subprocess.CompletedProcess(args, 1, '', 'start failed')
            self.active.add(unit)
            return subprocess.CompletedProcess(args, 0, '', '')
        raise AssertionError(f'unexpected command: {args}')


def make_release(root: Path, *, now: float, stable_age: int = 900) -> Path:
    releases = root / 'releases'
    release = releases / ('a' * 40)
    release.mkdir(parents=True)
    sample = release / 'runtime.txt'
    sample.write_text('immutable release fixture\n', encoding='utf-8')
    digest = hashlib.sha256(sample.read_bytes()).hexdigest()
    manifest = {
        'commit_sha': release.name,
        'file_count': 1,
        'files': [{'path': 'runtime.txt', 'sha256': digest}],
    }
    raw = json.dumps(manifest, sort_keys=True).encode()
    (release / 'HES_RELEASE_MANIFEST_v1.json').write_bytes(raw)
    manifest_hash = hashlib.sha256(raw).hexdigest()
    (release / 'HES_RELEASE_MANIFEST_v1.sha256').write_text(f'{manifest_hash}  HES_RELEASE_MANIFEST_v1.json\n')
    current = root / 'current'
    current.symlink_to(release, target_is_directory=True)
    os.utime(current, (now - stable_age, now - stable_age), follow_symlinks=False)
    return release


def health_report(inactive, extra=()):
    issues = []
    for unit in inactive:
        issues.append({'check': f'service:{unit}', 'state': 'CRITICAL', 'detail': 'not_active'})
        if unit == 'hes-strategy-paper-evaluator.service':
            issues += [
                {'check': 'freshness:trade_journal_v2.jsonl', 'state': 'CRITICAL', 'detail': 'stale'},
                {'check': 'freshness:strategy_policy_v2_eval_report.json', 'state': 'CRITICAL', 'detail': 'stale'},
            ]
        elif unit == 'hes-strategy-learning-loop.service':
            issues += [
                {'check': 'freshness:strategy_learning_v1_report.json', 'state': 'CRITICAL', 'detail': 'stale'},
                {'check': 'freshness:no_trade_decision_audit_24h_v1.jsonl', 'state': 'CRITICAL', 'detail': 'stale'},
            ]
        elif unit == 'hes-precision-entry-journal.service':
            issues.append({'check': 'freshness:precision_entry_journal_report_v1.json', 'state': 'CRITICAL', 'detail': 'stale'})
    issues.extend(extra)
    return {'overall': 'CRITICAL' if issues else 'OK', 'issues': issues}


def make_recovery(tmp_path, *, inactive=REPAIR_ORDER, extra=(), fail_start=(), now=2_000_000_000):
    root = tmp_path / 'app'
    make_release(root, now=now)
    state = tmp_path / 'state'
    runner = FakeSystemd(
        active=set(DEPENDENCIES[REPAIR_ORDER[0]]) | {DEPENDENCIES[REPAIR_ORDER[2]][0]},
        enabled=REPAIR_ORDER,
        fail_start=fail_start,
    )
    inactive_set = set(inactive)
    for unit in REPAIR_ORDER:
        if unit not in inactive_set:
            runner.active.add(unit)
    provider = lambda: health_report(inactive_set, extra)
    recovery = OperationalRecoveryV1(
        root=root, state_dir=state, runner=runner, health_provider=provider,
        clock=lambda: now, sleep=lambda _: None, startup_timeout_seconds=0,
    )
    return recovery, runner, root, state


def test_verified_release_manifest_is_required_and_checked(tmp_path):
    root = tmp_path / 'app'
    release = make_release(root, now=2_000_000_000)
    result = verify_active_release(root, now=2_000_000_000)
    assert result['release_id'] == release.name
    assert result['files_checked'] == 1
    (release / 'runtime.txt').write_text('tampered\n')
    with pytest.raises(Exception, match='RELEASE_FILE_HASH_MISMATCH'):
        verify_active_release(root, now=2_000_000_000)


def test_release_pointer_must_be_stable(tmp_path):
    root = tmp_path / 'app'
    make_release(root, now=2_000_000_000, stable_age=10)
    with pytest.raises(Exception, match='CURRENT_POINTER_NOT_STABLE'):
        verify_active_release(root, now=2_000_000_000)


def test_all_paper_workers_recover_in_dependency_order(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path)
    result = recovery.run()
    assert result['status'] == 'RECOVERED'
    starts = [cmd[-1] for cmd in runner.commands if cmd[:2] == ('systemctl', 'start')]
    assert starts == list(REPAIR_ORDER)
    assert all((state / 'repair-events.jsonl').read_text().count(unit) >= 2 for unit in REPAIR_ORDER)
    assert not any('gateio' in cmd[-1] and cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_unrelated_feed_or_integrity_issue_blocks_all_repair(tmp_path):
    extra = [{'check': 'integrity:gateio_1m_witness', 'state': 'CRITICAL', 'detail': 'failed'}]
    recovery, runner, _, _ = make_recovery(tmp_path, extra=extra)
    result = recovery.run()
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'UNRELATED_HEALTH_FAILURE'
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_deployment_lock_blocks_recovery(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path)
    state.mkdir(parents=True, exist_ok=True)
    with (state / 'deployment.lock').open('w') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = recovery.run()
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'DEPLOYMENT_LOCK_HELD'
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_manual_hold_marker_blocks_only_operator_requested_recovery(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path, inactive=[REPAIR_ORDER[0]])
    hold = state / 'hold'
    hold.mkdir(parents=True)
    (hold / f'{REPAIR_ORDER[0]}.hold').touch()
    result = recovery.run()
    assert result['status'] == 'BLOCKED'
    assert result['reason'].startswith('MANUAL_HOLD:')
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_failed_start_is_audited_and_does_not_cascade(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path, fail_start=[REPAIR_ORDER[0]])
    result = recovery.run()
    assert result['status'] == 'PARTIAL_OR_BLOCKED'
    assert result['actions'][0]['result'] == 'START_FAILED'
    assert len((state / 'repair-events.jsonl').read_text().splitlines()) == 2
    assert not any(cmd[:2] == ('systemctl', 'start') and cmd[-1] == REPAIR_ORDER[1] for cmd in runner.commands)


def test_retry_budget_prevents_repeated_start_loops(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path, inactive=[REPAIR_ORDER[0]])
    state.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromtimestamp(2_000_000_000 - 100, timezone.utc).isoformat()
    rows = [
        {'at': stamp, 'service': REPAIR_ORDER[0], 'action': 'START_ATTEMPT'},
        {'at': stamp, 'service': REPAIR_ORDER[0], 'action': 'START_ATTEMPT'},
    ]
    (state / 'repair-events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    result = recovery.run()
    assert result['actions'][0]['reason'] == 'RETRY_BUDGET_EXHAUSTED'
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_recovery_never_targets_feed_dashboard_or_order_services():
    assert set(REPAIR_ORDER) == {
        'hes-strategy-paper-evaluator.service',
        'hes-strategy-learning-loop.service',
        'hes-precision-entry-journal.service',
    }
    assert all('gateio' not in unit and 'dashboard' not in unit and 'execution' not in unit for unit in REPAIR_ORDER)


def test_deployment_lock_probe_detects_another_process(tmp_path):
    lock_path = tmp_path / 'state' / 'deployment.lock'
    lock_path.parent.mkdir(parents=True)
    with lock_path.open('w') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert deployment_lock_held(lock_path) is True
    assert deployment_lock_held(lock_path) is False


def test_systemd_monitor_is_scoped_and_read_only_except_health_state():
    service = Path('deploy/systemd/hes-operational-healthcheck.service').read_text()
    timer = Path('deploy/systemd/hes-operational-healthcheck.timer').read_text()
    assert 'ExecStart=/usr/bin/python3 -u /opt/hes-trade-agent/current/scripts/ops/hes_operational_healthcheck_v1.py' in service
    assert 'User=root' in service
    assert 'NoNewPrivileges=true' in service
    assert 'ProtectSystem=strict' in service
    assert 'ReadWritePaths=/var/lib/hes-operational-health' in service
    assert '/opt/hes-trade-agent/data/forward' not in service
    assert 'OnUnitActiveSec=5min' in timer
    assert 'Persistent=true' in timer


def test_retry_cooldown_prevents_an_early_second_attempt(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path, inactive=[REPAIR_ORDER[0]])
    state.mkdir(parents=True, exist_ok=True)
    stamp = datetime.fromtimestamp(2_000_000_000 - 600, timezone.utc).isoformat()
    (state / 'repair-events.jsonl').write_text(json.dumps({
        'at': stamp, 'service': REPAIR_ORDER[0], 'action': 'START_ATTEMPT'
    }) + '\n')
    result = recovery.run()
    assert result['actions'][0]['reason'] == 'RETRY_COOLDOWN'
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_corrupt_repair_audit_fails_closed(tmp_path):
    recovery, runner, _, state = make_recovery(tmp_path, inactive=[REPAIR_ORDER[0]])
    state.mkdir(parents=True, exist_ok=True)
    (state / 'repair-events.jsonl').write_text('{not-json}\n')
    with pytest.raises(Exception, match='REPAIR_AUDIT_CORRUPT'):
        recovery.run()
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)


def test_missing_feed_dependency_blocks_recovery(tmp_path):
    recovery, runner, _, _ = make_recovery(tmp_path, inactive=[REPAIR_ORDER[0]])
    runner.active.discard('hes-global-market-data-gateio-1h.service')
    recovery.health_provider = lambda: health_report(
        [REPAIR_ORDER[0]],
        [{'check':'service:hes-global-market-data-gateio-1h.service','state':'CRITICAL','detail':'not_active'}],
    )
    result = recovery.run()
    assert result['status'] == 'BLOCKED'
    assert result['reason'] == 'UNRELATED_HEALTH_FAILURE'
    assert not any(cmd[:2] == ('systemctl', 'start') for cmd in runner.commands)
