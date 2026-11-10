#!/usr/bin/env python3
"""Bounded, auditable recovery for approved paper-only workers.

Never restarts market-data feeds, the dashboard, network tunnel, or any order path.
All recovery is gated by a stable immutable release, healthy dependencies, a
non-held deployment lock, and a finite retry budget.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Iterator

ROOT = Path('/opt/hes-trade-agent')
STATE_DIR = Path('/var/lib/hes-operational-health')
DEPLOY_LOCK = STATE_DIR / 'deployment.lock'
AUDIT_PATH = STATE_DIR / 'repair-events.jsonl'
HOLD_DIR = STATE_DIR / 'hold'

REPAIR_ORDER = (
    'hes-strategy-paper-evaluator.service',
    'hes-strategy-learning-loop.service',
    'hes-precision-entry-journal.service',
)

DEPENDENCIES = {
    'hes-strategy-paper-evaluator.service': (
        'hes-global-market-data-gateio.service',
        'hes-global-market-data-gateio-1h.service',
        'hes-global-market-data-gateio-4h.service',
    ),
    'hes-strategy-learning-loop.service': (
        'hes-strategy-paper-evaluator.service',
    ),
    'hes-precision-entry-journal.service': (
        'hes-global-market-data-gateio-1m.service',
        'hes-strategy-paper-evaluator.service',
    ),
}

IGNORABLE_WHEN_INACTIVE = {
    'hes-strategy-paper-evaluator.service': {
        'service:hes-strategy-paper-evaluator.service',
        'freshness:trade_journal_v2.jsonl',
        'freshness:strategy_policy_v2_eval_report.json',
    },
    'hes-strategy-learning-loop.service': {
        'service:hes-strategy-learning-loop.service',
        'freshness:strategy_learning_v1_report.json',
        'freshness:no_trade_decision_audit_24h_v1.jsonl',
    },
    'hes-precision-entry-journal.service': {
        'service:hes-precision-entry-journal.service',
        'freshness:precision_entry_journal_report_v1.json',
        'precision:report',
    },
}


class RecoveryError(RuntimeError):
    pass


def _default_runner(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=10, **kwargs)


@contextmanager
def _exclusive_deployment_guard(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            acquired = False
        yield acquired
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def verify_active_release(root: Path, *, now: float, stable_seconds: int = 600) -> dict[str, Any]:
    current = root / 'current'
    releases = (root / 'releases').resolve()
    if not current.is_symlink():
        raise RecoveryError('CURRENT_POINTER_NOT_SYMLINK')
    if now - current.lstat().st_mtime < stable_seconds:
        raise RecoveryError('CURRENT_POINTER_NOT_STABLE')
    release = current.resolve(strict=True)
    if not release.is_relative_to(releases) or release == releases or release.parent != releases:
        raise RecoveryError('CURRENT_POINTER_OUTSIDE_RELEASES')
    manifest_path = release / 'HES_RELEASE_MANIFEST_v1.json'
    sidecar_path = release / 'HES_RELEASE_MANIFEST_v1.sha256'
    if not manifest_path.is_file() or not sidecar_path.is_file():
        raise RecoveryError('RELEASE_MANIFEST_MISSING')
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('commit_sha') != release.name:
        raise RecoveryError('RELEASE_ID_MISMATCH')
    files = manifest.get('files')
    if not isinstance(files, list) or manifest.get('file_count') != len(files):
        raise RecoveryError('RELEASE_FILE_COUNT_MISMATCH')
    checked = 0
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise RecoveryError('RELEASE_ENTRY_INVALID')
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise RecoveryError('RELEASE_PATH_UNSAFE')
        path = release / rel
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(release):
            raise RecoveryError('RELEASE_FILE_MISSING_OR_ESCAPED')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item.get('sha256'):
            raise RecoveryError('RELEASE_FILE_HASH_MISMATCH')
        checked += 1
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    sidecar_fields = sidecar_path.read_text(encoding='utf-8').strip().split()
    if len(sidecar_fields) < 2 or sidecar_fields[0] != manifest_hash or sidecar_fields[-1] != 'HES_RELEASE_MANIFEST_v1.json':
        raise RecoveryError('RELEASE_MANIFEST_HASH_MISMATCH')
    return {
        'release_id': release.name,
        'manifest_sha256': manifest_hash,
        'files_checked': checked,
        'stable_seconds': int(now - current.lstat().st_mtime),
    }


def deployment_lock_held(path: Path = DEPLOY_LOCK) -> bool:
    """Return True only when another process owns the exclusive deployment lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
    finally:
        os.close(fd)


class OperationalRecoveryV1:
    def __init__(
        self,
        *,
        root: Path = ROOT,
        state_dir: Path = STATE_DIR,
        runner: Callable[..., subprocess.CompletedProcess[str]] = _default_runner,
        health_provider: Callable[[], dict[str, Any]],
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        stable_seconds: int = 600,
        cooldown_seconds: int = 900,
        max_attempts_per_hour: int = 2,
        startup_timeout_seconds: int = 25,
    ) -> None:
        self.root = root
        self.state_dir = state_dir
        self.runner = runner
        self.health_provider = health_provider
        self.clock = clock
        self.sleep = sleep
        self.stable_seconds = stable_seconds
        self.cooldown_seconds = cooldown_seconds
        self.max_attempts_per_hour = max_attempts_per_hour
        self.startup_timeout_seconds = startup_timeout_seconds
        self.audit_path = state_dir / 'repair-events.jsonl'
        self.deploy_lock = state_dir / 'deployment.lock'
        self.hold_dir = state_dir / 'hold'

    def _active(self, unit: str) -> bool:
        result = self.runner(['systemctl', 'is-active', '--quiet', unit])
        return result.returncode == 0

    def _enabled(self, unit: str) -> bool:
        result = self.runner(['systemctl', 'is-enabled', '--quiet', unit])
        return result.returncode == 0

    def _audit(self, event: dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.audit_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            payload = (json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n').encode()
            offset = 0
            while offset < len(payload):
                offset += os.write(fd, payload[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)

    def _attempt_history(self, unit: str) -> list[dict[str, Any]]:
        if not self.audit_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.audit_path.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RecoveryError('REPAIR_AUDIT_CORRUPT') from exc
            if row.get('service') == unit and row.get('action') == 'START_ATTEMPT':
                rows.append(row)
        return rows

    def _retry_allowed(self, unit: str, now: float) -> tuple[bool, str, int]:
        history = self._attempt_history(unit)
        recent = []
        for row in history:
            try:
                parsed = datetime.fromisoformat(row['at'].replace('Z', '+00:00'))
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ValueError('timestamp_not_timezone_aware')
                stamp = parsed.timestamp()
            except Exception as exc:
                raise RecoveryError('REPAIR_AUDIT_TIMESTAMP_INVALID') from exc
            if stamp > now + 60:
                raise RecoveryError('REPAIR_AUDIT_CLOCK_SKEW')
            if 0 <= now - stamp < 3600:
                recent.append((stamp, row))
        if len(recent) >= self.max_attempts_per_hour:
            return False, 'RETRY_BUDGET_EXHAUSTED', len(recent)
        if recent and now - max(item[0] for item in recent) < self.cooldown_seconds:
            return False, 'RETRY_COOLDOWN', len(recent)
        return True, 'RETRY_ALLOWED', len(recent)

    def _preflight(self, inactive: set[str]) -> tuple[bool, list[dict[str, str]]]:
        report = self.health_provider()
        if not isinstance(report, dict) or not isinstance(report.get('issues'), list):
            raise RecoveryError('HEALTH_REPORT_INVALID')
        issues = report['issues']
        for issue in issues:
            if (
                not isinstance(issue, dict)
                or not isinstance(issue.get('check'), str)
                or not issue['check']
                or issue.get('state') not in ('WARN', 'CRITICAL')
            ):
                raise RecoveryError('HEALTH_ISSUE_INVALID')
        allowed = set()
        for unit in inactive:
            allowed.update(IGNORABLE_WHEN_INACTIVE[unit])
        unexpected = [
            issue for issue in issues
            if issue['check'] not in allowed
        ]
        return not unexpected, unexpected

    def _wait_ready(self, unit: str, inactive_remaining: set[str]) -> bool:
        """Require both systemd activity and a fresh, clean health snapshot.

        Other workers that have not yet been recovered may retain only their
        explicitly allowlisted inactive-service/freshness issues. Any unrelated
        health issue, including one that appears after startup, blocks the chain.
        The bounded poll count also prevents a frozen test/system clock from
        turning readiness into an unbounded loop.
        """
        for attempt in range(max(1, self.startup_timeout_seconds + 1)):
            if self._active(unit):
                try:
                    healthy, _ = self._preflight(inactive_remaining)
                except Exception:
                    return False
                if healthy:
                    return True
            if attempt < self.startup_timeout_seconds:
                self.sleep(1)
        return False

    def run(self) -> dict[str, Any]:
        now = self.clock()
        inactive = {unit for unit in REPAIR_ORDER if not self._active(unit)}
        if not inactive:
            return {'status': 'NO_ACTION', 'reason': 'ALL_REPAIRABLE_SERVICES_ACTIVE', 'actions': []}

        with _exclusive_deployment_guard(self.deploy_lock) as acquired:
            if not acquired:
                return {'status': 'BLOCKED', 'reason': 'DEPLOYMENT_LOCK_HELD', 'actions': []}
            try:
                release = verify_active_release(self.root, now=now, stable_seconds=self.stable_seconds)
            except Exception as exc:
                return {'status': 'BLOCKED', 'reason': str(exc)[:160], 'actions': []}

            for unit in inactive:
                if (self.hold_dir / f'{unit}.hold').exists():
                    return {'status': 'BLOCKED', 'reason': f'MANUAL_HOLD:{unit}', 'actions': []}

            preflight_ok, unexpected = self._preflight(inactive)
            if not preflight_ok:
                return {
                    'status': 'BLOCKED', 'reason': 'UNRELATED_HEALTH_FAILURE',
                    'issues': unexpected[:20], 'release_id': release['release_id'], 'actions': [],
                }

            actions: list[dict[str, Any]] = []
            for unit in REPAIR_ORDER:
                if unit not in inactive or self._active(unit):
                    continue
                deps = DEPENDENCIES[unit]
                missing_deps = [dep for dep in deps if not self._active(dep)]
                if missing_deps:
                    actions.append({'service': unit, 'result': 'SKIPPED', 'reason': 'DEPENDENCY_NOT_ACTIVE', 'dependencies': missing_deps})
                    continue
                if not self._enabled(unit):
                    actions.append({'service': unit, 'result': 'SKIPPED', 'reason': 'SERVICE_NOT_ENABLED'})
                    continue
                allowed, reason, attempts = self._retry_allowed(unit, now)
                if not allowed:
                    actions.append({'service': unit, 'result': 'SKIPPED', 'reason': reason, 'attempts_last_hour': attempts})
                    continue

                event = {
                    'schema': 'hes_operational_repair_event_v1',
                    'at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
                    'service': unit,
                    'action': 'START_ATTEMPT',
                    'reason': 'SERVICE_INACTIVE_AFTER_RELEASE_STABLE',
                    'release_id': release['release_id'],
                    'attempts_last_hour_before': attempts,
                    'execution_enabled': False,
                    'orders_placed': False,
                }
                self._audit(event)
                started = self.runner(['systemctl', 'start', unit])
                if started.returncode != 0:
                    recovered = False
                    result = 'START_FAILED'
                else:
                    recovered = self._wait_ready(unit, inactive - {unit})
                    result = 'RECOVERED' if recovered else 'READINESS_FAILED'
                self._audit({**event, 'action': 'START_RESULT', 'result': result, 'systemctl_returncode': started.returncode})
                actions.append({'service': unit, 'result': result, 'systemctl_returncode': started.returncode})
                if not recovered:
                    break

            status = 'RECOVERED' if any(item['result'] == 'RECOVERED' for item in actions) else ('NO_ACTION' if not actions else 'PARTIAL_OR_BLOCKED')
            return {'status': status, 'release_id': release['release_id'], 'actions': actions}


def main() -> int:
    from hes_runtime_healthcheck_v1 import collect_checks
    recovery = OperationalRecoveryV1(health_provider=collect_checks)
    result = recovery.run()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] in ('NO_ACTION', 'RECOVERED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
