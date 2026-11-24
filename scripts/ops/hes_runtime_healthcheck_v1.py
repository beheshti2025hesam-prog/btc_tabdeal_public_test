#!/usr/bin/env python3
"""Read-only HES runtime integrity checks. No service or trading mutations."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

if __package__:
    from .hes_capacity_trend_v1 import inode_free_check
else:
    from hes_capacity_trend_v1 import inode_free_check

CODE_ROOT = Path(__file__).resolve().parents[2]
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))
from forward.sealed_jsonl_segments_v1 import has_sealed_segments, read_jsonl_records

ROOT = Path('/opt/hes-trade-agent')
DATA = ROOT / 'data' / 'forward'
WITNESS = Path('/var/lib/hes-gateio-1m-integrity/observations.jsonl')

SERVICE_UNITS = (
    'hes-global-market-data-gateio.service',
    'hes-global-market-data-gateio-1m.service',
    'hes-global-market-data-gateio-1m-integrity.timer',
    'hes-global-market-data-gateio-1h.service',
    'hes-global-market-data-gateio-4h.service',
    'hes-strategy-paper-evaluator.service',
    'hes-strategy-learning-loop.service',
    'hes-precision-entry-journal.service',
    'hes-indicator-strategy-forward-paper.service',
    'hes-readonly-dashboard.service',
)

FRESHNESS_LIMITS = {
    'global_market_candles_1m_v1.jsonl': 120,
    'global_market_candles_v1.jsonl': 30 * 60,
    'global_market_candles_1h_v1.jsonl': 2 * 60 * 60,
    'global_market_candles_4h_v1.jsonl': 6 * 60 * 60,
    'trade_journal_v2.jsonl': 30 * 60,
    'strategy_policy_v2_eval_report.json': 5 * 60,
    'strategy_learning_v1_report.json': 10 * 60,
    'no_trade_decision_audit_24h_v1.jsonl': 45 * 60,
    'precision_entry_journal_report_v1.json': 120,
    'indicator_strategy_forward_paper_report_v1.json': 120,
    'strategy_family_results_report_v1.json': 120,
}


def _parse_aware_timestamp(value: Any) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ValueError('timestamp_missing')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('timestamp_timezone_missing')
    return parsed.timestamp()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return read_jsonl_records(path)


def _check_indicator_forward_paper(data: Path, add: Callable[[str, str, str], None]) -> None:
    """Verify the observer's isolated research ledgers and fail-closed safety flags."""
    report_path = data / 'indicator_strategy_forward_paper_report_v1.json'
    state_path = data / 'indicator_strategy_forward_paper_state_v1.json'
    if report_path.exists():
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            if not isinstance(report, dict) or report.get('schema') != 'hes_indicator_strategy_forward_paper_report_v1':
                raise ValueError('report_schema_invalid')
            identity_ok = report.get('source') == 'gateio_public_spot' and report.get('symbol') == 'BTC_USDT'
            add('indicator_forward:source_identity', 'OK' if identity_ok else 'CRITICAL',
                'gateio_public_spot/BTC_USDT' if identity_ok else 'source_or_symbol_mismatch')
            safety = report.get('safety')
            safe = (
                isinstance(safety, dict)
                and safety.get('research_only') is True
                and safety.get('performance_eligible') is False
                and safety.get('training_label_eligible') is False
                and safety.get('decision_authority') is False
                and safety.get('candidate_generation_authorized') is False
                and safety.get('risk_gate_bypass') is False
                and safety.get('execution_enabled') is False
                and safety.get('orders_placed') is False
            )
            add('indicator_forward:paper_only', 'OK' if safe else 'CRITICAL',
                'all_safety_flags_locked' if safe else 'unsafe_or_missing_safety_flags')

            specs = (
                ('indicator_strategy_forward_paper_journal_v1.jsonl', 'decision_records'),
                ('indicator_strategy_forward_paper_outcomes_v1.jsonl', 'outcome_records'),
            )
            decision_ids: set[str] = set()
            for filename, count_key in specs:
                expected = report.get(count_key)
                if type(expected) is not int or expected < 0:
                    raise ValueError(f'{count_key}_invalid')
                path = data / filename
                if not path.exists():
                    rows = []
                    if expected:
                        add(f'indicator_forward:{filename}:count', 'CRITICAL', f'missing_but_reported_count={expected}')
                    else:
                        add(f'indicator_forward:{filename}:count', 'OK', 'empty_ledger_not_yet_created')
                else:
                    rows = _load_jsonl(path)
                    add(f'indicator_forward:{filename}:count',
                        'OK' if len(rows) == expected else 'CRITICAL', f'{len(rows)}!={expected}' if len(rows) != expected else f'{len(rows)}_records')
                ids = [str(row.get('event_id') or '') for row in rows]
                identity_safe = bool(all(ids)) and len(ids) == len(set(ids))
                add(f'indicator_forward:{filename}:identity', 'OK' if identity_safe else 'CRITICAL',
                    'unique_event_ids' if identity_safe else 'missing_or_duplicate_event_id')
                if filename.endswith('_journal_v1.jsonl'):
                    decision_ids.update(ids)
                    row_safe = all(
                        row.get('research_only') is True
                        and row.get('performance_eligible') is False
                        and row.get('training_label_eligible') is False
                        and row.get('decision_authority') is False
                        and row.get('candidate_generation_authorized') is False
                        and row.get('risk_gate_bypass') is False
                        and row.get('execution_enabled') is False
                        and row.get('orders_placed') is False
                        and row.get('evidence_source') == 'gateio_public_spot'
                        and row.get('symbol') == 'BTC_USDT'
                        and row.get('timeframe') == '15m'
                        and row.get('entry_timeframe') == '1m'
                        for row in rows
                    )
                else:
                    row_safe = all(
                        row.get('research_only') is True
                        and row.get('performance_eligible') is False
                        and row.get('training_label_eligible') is False
                        and row.get('decision_authority') is False
                        and row.get('execution_enabled') is False
                        and row.get('orders_placed') is False
                        and row.get('symbol') == 'BTC_USDT'
                        and row.get('timeframe') == '15m'
                        and row.get('entry_timeframe') == '1m'
                        and row.get('candidate_event_id') in decision_ids
                        and (row.get('direction') != 'SHORT' or row.get('economics_status') == 'NOT_ECONOMICALLY_VALIDATED_FROM_SPOT')
                        for row in rows
                    )
                add(f'indicator_forward:{filename}:paper_only', 'OK' if row_safe else 'CRITICAL',
                    'records_research_only_and_linked' if row_safe else 'unsafe_or_unlinked_record')
        except Exception as exc:
            add('indicator_forward:integrity', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')
    else:
        add('indicator_forward:report_missing', 'CRITICAL', 'report_missing')

    if not state_path.exists():
        add('indicator_forward:state_missing', 'CRITICAL', 'state_missing')
    else:
        try:
            state = json.loads(state_path.read_text(encoding='utf-8'))
            valid = (
                isinstance(state, dict)
                and state.get('schema') == 'hes_indicator_strategy_forward_paper_state_v2'
                and state.get('bootstrap_mode') == 'NO_RETROACTIVE_TRADES'
                and type(state.get('last_processed_1m_open_time')) is int
                and type(state.get('last_processed_signal_close_time')) is int
                and type(state.get('processed_1m_bars')) is int
                and state.get('processed_1m_bars') >= 0
                and isinstance(state.get('active'), dict)
                and set(state.get('active', {})).issubset({'trend_confirmation', 'momentum_breakout', 'range_mean_reversion'})
            )
            add('indicator_forward:state_integrity', 'OK' if valid else 'CRITICAL',
                'valid_forward_only_cursor' if valid else 'state_schema_or_cursor_invalid')
        except Exception as exc:
            add('indicator_forward:state_integrity', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')


def collect_checks(
    *, root: Path = ROOT,
    now: float | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Return deterministic health evidence; callers decide whether to act."""
    data = root / 'data' / 'forward'
    now_s = time.time() if now is None else float(now)
    checks: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []

    def add(name: str, state: str, detail: str) -> None:
        checks.append({'check': name, 'state': state, 'detail': detail})
        if state in ('WARN', 'CRITICAL'):
            issues.append({'check': name, 'state': state, 'detail': detail})

    def service_active(unit: str) -> bool:
        result = runner(
            ['systemctl', 'is-active', '--quiet', unit],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0

    for unit in SERVICE_UNITS:
        try:
            active = service_active(unit)
        except Exception as exc:
            active, detail = False, f'probe_error:{type(exc).__name__}'
        else:
            detail = 'active' if active else 'not_active'
        add(f'service:{unit}', 'OK' if active else 'CRITICAL', detail)

    for filename, max_age in FRESHNESS_LIMITS.items():
        path = data / filename
        if not path.exists() and not has_sealed_segments(path):
            add(f'freshness:{filename}', 'CRITICAL', 'file_missing')
            continue
        try:
            if path.suffix == '.jsonl':
                rows = _load_jsonl(path)
                if not rows:
                    raise ValueError('empty_jsonl')
                stamp = rows[-1].get('observed_at')
                observed = _parse_aware_timestamp(stamp) if stamp else path.stat().st_mtime
            else:
                payload = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(payload, dict):
                    raise ValueError('report_not_object')
                observed = _parse_aware_timestamp(payload.get('updated_at'))
            age = now_s - observed
            state = 'OK' if -60 <= age <= max_age else 'CRITICAL'
            detail = f'{age:.1f}s' if age >= 0 else 'timestamp_in_future'
            add(f'freshness:{filename}', state, detail)
        except Exception as exc:
            add(f'integrity:{filename}', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')

    strategy_report_path = data / 'strategy_policy_v2_eval_report.json'
    if strategy_report_path.exists():
        try:
            strategy_report = json.loads(strategy_report_path.read_text(encoding='utf-8'))
            if not isinstance(strategy_report, dict):
                raise ValueError('strategy_report_not_object')
            safe = strategy_report.get('execution_enabled') is False and strategy_report.get('orders_placed') is False
            add('strategy:paper_only', 'OK' if safe else 'CRITICAL', 'flags_safe' if safe else 'unsafe_report_flags')
            identity_ok = strategy_report.get('source') == 'gateio_public_spot' and strategy_report.get('symbol') == 'BTC_USDT'
            add('strategy:source_identity', 'OK' if identity_ok else 'CRITICAL', 'gateio_public_spot/BTC_USDT' if identity_ok else 'source_or_symbol_mismatch')
        except Exception as exc:
            add('strategy:report_integrity', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')
    # Missing reports are already covered by the freshness gate above; an inactive
    # evaluator may recreate them, while malformed/unsafe reports remain critical.

    if not WITNESS.exists():
        add('integrity:gateio_1m_witness', 'CRITICAL', 'witness_missing')
    else:
        try:
            witness_rows = _load_jsonl(WITNESS)
            if not witness_rows:
                raise ValueError('witness_empty')
            latest = witness_rows[-1]
            observed = _parse_aware_timestamp(latest.get('observed_at'))
            age = now_s - observed
            valid = (
                latest.get('status') == 'PASS'
                and latest.get('source') == 'gateio_public_spot'
                and latest.get('symbol') == 'BTC_USDT'
                and latest.get('timeframe') == '1m'
                and latest.get('execution_enabled') is False
                and latest.get('orders_placed') is False
                and type(latest.get('latest_age_seconds')) in (int, float)
                and 0 <= latest['latest_age_seconds'] <= 120
                # A witness can be written after now_s is sampled; tolerate bounded clock/read skew.
                and -60 <= age <= 600
            )
            add('integrity:gateio_1m_witness', 'OK' if valid else 'CRITICAL',
                f"status={latest.get('status')!r}; candle_age={latest.get('latest_age_seconds')!r}; witness_age={age:.1f}s")
        except Exception as exc:
            add('integrity:gateio_1m_witness', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')

    journal = data / 'trade_journal_v2.jsonl'
    if journal.exists() or has_sealed_segments(journal):
        try:
            rows = _load_jsonl(journal)
            ids: set[str] = set()
            duplicates = 0
            unsafe = 0
            for row in rows:
                event_id = row.get('event_id')
                if event_id:
                    if event_id in ids:
                        duplicates += 1
                    ids.add(str(event_id))
                if row.get('execution_enabled') is not False or row.get('orders_placed') is not False:
                    unsafe += 1
            add('journal:jsonl', 'OK', f'{len(rows)} records; malformed=0')
            add('journal:unique-event-ids', 'OK' if duplicates == 0 else 'CRITICAL', f'duplicates={duplicates}')
            add('journal:paper-only', 'OK' if unsafe == 0 else 'CRITICAL', f'unsafe_records={unsafe}')
        except Exception as exc:
            add('journal:integrity', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')
    else:
        add('journal:integrity', 'CRITICAL', 'canonical_journal_missing')

    precision_report_path = data / 'precision_entry_journal_report_v1.json'
    if precision_report_path.exists():
        try:
            precision_report = json.loads(precision_report_path.read_text(encoding='utf-8'))
            if not isinstance(precision_report, dict):
                raise ValueError('precision_report_not_object')
            if precision_report.get('execution_enabled') is not False or precision_report.get('orders_placed') is not False:
                add('precision:paper_only', 'CRITICAL', 'unsafe_report_flags')
            ledger_specs = (
                ('precision_entry_events_v1.jsonl', 'event_count'),
                ('precision_entry_candidates_v1.jsonl', 'candidate_count'),
                ('precision_entry_outcomes_v1.jsonl', 'outcome_count'),
            )
            candidate_rows: list[dict[str, Any]] = []
            for filename, count_key in ledger_specs:
                path = data / filename
                expected = precision_report.get(count_key)
                if type(expected) is not int or expected < 0:
                    raise ValueError(f'{count_key}_invalid')
                if not path.exists():
                    if expected != 0:
                        add(f'precision:{filename}', 'CRITICAL', f'missing_but_reported_count={expected}')
                    else:
                        add(f'precision:{filename}', 'OK', 'empty_ledger_not_yet_created')
                    continue
                rows = _load_jsonl(path)
                if len(rows) != expected:
                    add(f'precision:{filename}', 'CRITICAL', f'count_mismatch:{len(rows)}!={expected}')
                else:
                    add(f'precision:{filename}', 'OK', f'{len(rows)} records')
                ids = [str(row.get('event_id') or '') for row in rows]
                if any(not item for item in ids) or len(ids) != len(set(ids)):
                    add(f'precision:{filename}:identity', 'CRITICAL', 'missing_or_duplicate_event_id')
                if any(row.get('execution_enabled') is not False or row.get('orders_placed') is not False for row in rows):
                    add(f'precision:{filename}:paper_only', 'CRITICAL', 'unsafe_record_flags')
                if any(row.get('source') != 'gateio_public_spot' or row.get('symbol') != 'BTC_USDT' or row.get('timeframe') != '1m' for row in rows):
                    add(f'precision:{filename}:source_identity', 'CRITICAL', 'source_symbol_or_timeframe_mismatch')
                if filename == 'precision_entry_candidates_v1.jsonl':
                    candidate_rows = rows
            cap = precision_report.get('daily_signal_cap')
            if cap != 3 or precision_report.get('daily_signal_cap_is_quota') is not False:
                add('precision:daily_cap_contract', 'CRITICAL', 'daily_cap_contract_mismatch')
            counts: dict[str, int] = {}
            for row in candidate_rows:
                entry_time = row.get('entry_time')
                if type(entry_time) is not int:
                    raise ValueError('candidate_entry_time_invalid')
                day = datetime.fromtimestamp(entry_time, timezone.utc).date().isoformat()
                counts[day] = counts.get(day, 0) + 1
            max_daily = max(counts.values(), default=0)
            add('precision:daily_signal_cap', 'OK' if max_daily <= 3 else 'CRITICAL', f'max_per_utc_day={max_daily}')
        except Exception as exc:
            add('precision:integrity', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')
    else:
        add('precision:report', 'CRITICAL', 'precision_report_missing')

    _check_indicator_forward_paper(data, add)

    try:
        usage = shutil.disk_usage(root)
        free_pct = 100.0 * usage.free / usage.total
        state = 'OK' if free_pct >= 15 else ('WARN' if free_pct >= 10 else 'CRITICAL')
        add('disk-free', state, f'{free_pct:.1f}%')
    except Exception as exc:
        add('disk-free', 'CRITICAL', f'{type(exc).__name__}:{str(exc)[:120]}')

    inode_state, inode_detail = inode_free_check(root)
    add('inode-free', inode_state, inode_detail)

    overall = 'CRITICAL' if any(item['state'] == 'CRITICAL' for item in issues) else ('WARN' if issues else 'OK')
    return {
        'schema': 'hes_runtime_healthcheck_v1',
        'checked_at': datetime.fromtimestamp(now_s, timezone.utc).isoformat(),
        'overall': overall,
        'checks': checks,
        'issues': issues,
    }


def main() -> int:
    report = collect_checks()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 2 if report['overall'] == 'CRITICAL' else 1 if report['overall'] == 'WARN' else 0


if __name__ == '__main__':
    raise SystemExit(main())
