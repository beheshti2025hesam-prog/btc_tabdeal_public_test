#!/usr/bin/env python3
"""Five-minute operational monitor with tightly bounded paper-worker recovery."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import syslog
import time
from typing import Any

if __package__:
    from .hes_capacity_trend_v1 import collect_capacity_trend
    from .hes_runtime_healthcheck_v1 import collect_checks
    from .hes_operational_recovery_v1 import DEPLOY_LOCK, OperationalRecoveryV1, deployment_lock_held, verify_active_release
else:  # systemd executes this file directly from the immutable release
    from hes_capacity_trend_v1 import collect_capacity_trend
    from hes_runtime_healthcheck_v1 import collect_checks
    from hes_operational_recovery_v1 import DEPLOY_LOCK, OperationalRecoveryV1, deployment_lock_held, verify_active_release

ROOT = Path('/opt/hes-trade-agent')
STATE_DIR = Path('/var/lib/hes-operational-health')
ISSUES_FILE = STATE_DIR / 'last-issues'


def _host_checks() -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(check: str, state: str, detail: str) -> None:
        if state != 'OK':
            issues.append({'check': check, 'state': state, 'detail': detail})

    try:
        usage = shutil.disk_usage('/')
        used_pct = 100.0 * usage.used / usage.total
        add('root-disk', 'CRITICAL' if used_pct >= 85 else 'OK', f'{used_pct:.1f}%_used')
    except Exception as exc:
        add('root-disk', 'CRITICAL', type(exc).__name__)

    try:
        trend = collect_capacity_trend(
            root=ROOT,
            state_path=STATE_DIR / 'capacity-trend-v1.json',
        )
        add('disk-growth-forecast', trend.get('state', 'WARN'), trend.get('detail', 'capacity_forecast_unknown'))
    except Exception as exc:
        add('disk-growth-forecast', 'WARN', f'capacity_trend_error:{type(exc).__name__}')

    try:
        ntp = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized', '--value'], capture_output=True, text=True, timeout=5)
        add('ntp', 'OK' if ntp.stdout.strip() == 'yes' and ntp.returncode == 0 else 'CRITICAL', ntp.stdout.strip() or 'not_synchronized')
    except Exception as exc:
        add('ntp', 'CRITICAL', type(exc).__name__)

    try:
        sockets = subprocess.run(['ss', '-lnt'], capture_output=True, text=True, timeout=5)
        socket_text = sockets.stdout
        add('ssh-port-9011', 'OK' if ':9011' in socket_text else 'CRITICAL', 'listening' if ':9011' in socket_text else 'not_listening')
        add('tunnel-port-443', 'OK' if ':443' in socket_text else 'CRITICAL', 'listening' if ':443' in socket_text else 'not_listening')
    except Exception as exc:
        add('socket-listeners', 'CRITICAL', type(exc).__name__)

    try:
        result = subprocess.run(['systemctl', 'is-active', '--quiet', 'xray.service'], capture_output=True, text=True, timeout=5)
        add('service:xray.service', 'OK' if result.returncode == 0 else 'CRITICAL', 'active' if result.returncode == 0 else 'not_active')
    except Exception as exc:
        add('service:xray.service', 'CRITICAL', type(exc).__name__)
    return issues


def _recovery_health_report(
    runtime: dict[str, Any],
    host_issues: list[dict[str, str]],
) -> dict[str, Any]:
    """Include host-level failures in the recovery preflight, not just reporting."""
    return {
        **runtime,
        "issues": [*runtime.get("issues", []), *host_issues],
    }


def _record_state(issues: list[dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    new_state = '\n'.join(sorted(f"{row['check']}:{row['detail']}" for row in issues))
    old_state = ISSUES_FILE.read_text(encoding='utf-8') if ISSUES_FILE.exists() else ''
    if new_state != old_state:
        if new_state:
            syslog.syslog(syslog.LOG_DAEMON | syslog.LOG_ERR, 'ALERT: HES operational health failed: ' + ';'.join(new_state.splitlines()))
        elif old_state:
            syslog.syslog(syslog.LOG_DAEMON | syslog.LOG_NOTICE, 'RECOVERY: HES operational health checks pass')
        else:
            syslog.syslog(syslog.LOG_DAEMON | syslog.LOG_NOTICE, 'INITIALIZED: HES operational health monitor active')
        temp = ISSUES_FILE.with_suffix('.tmp')
        temp.write_text(new_state, encoding='utf-8')
        os.chmod(temp, 0o600)
        os.replace(temp, ISSUES_FILE)


def main() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if deployment_lock_held(DEPLOY_LOCK):
        report = {
            'schema': 'hes_operational_healthcheck_v1',
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'overall': 'MAINTENANCE',
            'reason': 'DEPLOYMENT_LOCK_HELD',
            'execution_enabled': False,
            'orders_placed': False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    now = time.time()
    try:
        release = verify_active_release(ROOT, now=now)
        release_check = {'check': 'release-integrity', 'state': 'OK', 'detail': f"{release['release_id']}:{release['files_checked']} files"}
    except Exception as exc:
        release_check = {'check': 'release-integrity', 'state': 'CRITICAL', 'detail': f'{type(exc).__name__}:{str(exc)[:120]}'}
    # Collect every precondition before attempting recovery. Host failures (NTP,
    # SSH/tunnel listeners, Xray, and root-disk pressure) must veto worker starts
    # just like feed, journal, and data-integrity failures.
    preflight_runtime = collect_checks()
    preflight_host_issues = _host_checks()
    if release_check['state'] == 'OK':
        try:
            recovery = OperationalRecoveryV1(
                health_provider=lambda: _recovery_health_report(
                    preflight_runtime, preflight_host_issues
                )
            ).run()
        except Exception as exc:
            recovery = {'status': 'BLOCKED', 'reason': f'RECOVERY_ERROR:{type(exc).__name__}:{str(exc)[:120]}', 'actions': []}
    else:
        recovery = {'status': 'BLOCKED', 'reason': 'RELEASE_INTEGRITY_FAILED', 'actions': []}

    # Re-sample after recovery so the operator-facing report reflects the
    # resulting runtime state rather than only the preflight snapshot.
    runtime = collect_checks()
    host_issues = _host_checks()
    all_issues = list(runtime['issues']) + host_issues
    if release_check['state'] != 'OK':
        all_issues.append(release_check)
    recovery_check = {
        'check': 'bounded-recovery',
        'state': 'OK' if recovery.get('status') in ('NO_ACTION', 'RECOVERED') else 'WARN',
        'detail': recovery.get('status', 'UNKNOWN') + ':' + recovery.get('reason', 'completed'),
    }
    if recovery_check['state'] != 'OK':
        all_issues.append(recovery_check)

    _record_state(all_issues)
    overall = 'CRITICAL' if any(row['state'] == 'CRITICAL' for row in all_issues) else ('WARN' if all_issues else 'OK')
    report = {
        'schema': 'hes_operational_healthcheck_v1',
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'overall': overall,
        'release': release_check,
        'recovery': recovery,
        'runtime': runtime,
        'host_issues': host_issues,
        'issues': all_issues,
        'execution_enabled': False,
        'orders_placed': False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if overall == 'CRITICAL' else 1 if overall == 'WARN' else 0


if __name__ == '__main__':
    raise SystemExit(main())
