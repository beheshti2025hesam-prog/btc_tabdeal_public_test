"""Read-only projection of the canonical HES Strategy Policy V2 evaluator."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json, os
from pathlib import Path
from typing import Any
from forward.trade_journal_view_v1 import read_decision_journal, JournalProjectionError
from forward.strategy_entry_context_v1 import verify_entry_context

DEFAULT_REPORT_PATH = Path("/opt/hes-trade-agent/data/forward/strategy_policy_v2_eval_report.json")
DEFAULT_JOURNAL_PATH = Path("/opt/hes-trade-agent/data/forward/trade_journal_v2.jsonl")
EXPECTED_SCHEMA = "hes_strategy_policy_v2_forward_evaluation"
EXPECTED_SOURCE = "gateio_public_spot"
EXPECTED_SYMBOL = "BTC_USDT"
EXPECTED_POLICY_VERSION = "hes-btcusdt-mtf-confirmed-breakout-v2.0.0"

class StrategyV2DashboardError(ValueError):
    """Canonical V2 evidence is unavailable or unsafe to display."""

def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise StrategyV2DashboardError("invalid_report_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StrategyV2DashboardError("invalid_report_timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StrategyV2DashboardError("naive_report_timestamp")
    return parsed.astimezone(timezone.utc)

def _validated_market_data_provenance(report, gate, closed_15m_candle_time):
    provenance = report.get("market_data_provenance")
    if not isinstance(provenance, dict):
        raise StrategyV2DashboardError("v2_market_data_provenance_missing")
    if gate.get("market_data_provenance") != provenance:
        raise StrategyV2DashboardError("v2_gate_market_data_provenance_mismatch")
    if (
        provenance.get("schema") != "hes_market_data_batch_provenance_v1"
        or provenance.get("source") != EXPECTED_SOURCE
        or provenance.get("symbol") != EXPECTED_SYMBOL
        or provenance.get("batch_limit") != 240
    ):
        raise StrategyV2DashboardError("v2_market_data_provenance_identity_invalid")
    timeframes = provenance.get("timeframes")
    if not isinstance(timeframes, dict) or set(timeframes) != {"15m", "1h", "4h"}:
        raise StrategyV2DashboardError("v2_market_data_provenance_timeframes_invalid")
    for timeframe, item in timeframes.items():
        if not isinstance(item, dict):
            raise StrategyV2DashboardError("v2_market_data_provenance_entry_invalid:" + timeframe)
        digest = item.get("input_batch_sha256")
        count = item.get("candle_count")
        last_close = item.get("last_closed_candle_time")
        if (
            not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or isinstance(count, bool) or not isinstance(count, int) or not 200 <= count <= 240
            or isinstance(last_close, bool) or not isinstance(last_close, int) or last_close <= 0
        ):
            raise StrategyV2DashboardError("v2_market_data_provenance_entry_invalid:" + timeframe)
    if timeframes["15m"]["last_closed_candle_time"] != closed_15m_candle_time:
        raise StrategyV2DashboardError("v2_market_data_provenance_candle_mismatch")
    return provenance


def read_strategy_v2_dashboard(*, report_path=None, journal_path=None, now=None,
                               max_age_seconds=1800, journal_limit=20):
    if isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int) or max_age_seconds < 1:
        raise StrategyV2DashboardError("invalid_freshness_policy")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise StrategyV2DashboardError("verifier_clock_not_timezone_aware")
    current = current.astimezone(timezone.utc)
    report_file = Path(report_path or os.environ.get("HES_STRATEGY_V2_REPORT_PATH", str(DEFAULT_REPORT_PATH)))
    try:
        if report_file.is_symlink() or not report_file.is_file() or report_file.stat().st_size > 1_000_000:
            raise StrategyV2DashboardError("v2_report_unavailable_or_invalid")
        raw = report_file.read_bytes()
        report = json.loads(raw.decode("utf-8", errors="strict"))
    except StrategyV2DashboardError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrategyV2DashboardError("v2_report_unavailable_or_invalid") from exc
    if not isinstance(report, dict) or report.get("schema") != EXPECTED_SCHEMA:
        raise StrategyV2DashboardError("v2_report_schema_mismatch")
    if report.get("source") != EXPECTED_SOURCE or report.get("symbol") != EXPECTED_SYMBOL:
        raise StrategyV2DashboardError("v2_report_market_identity_mismatch")
    version = report.get("policy_version")
    if not isinstance(version, str) or not version:
        raise StrategyV2DashboardError("v2_policy_version_missing")
    if version != EXPECTED_POLICY_VERSION:
        raise StrategyV2DashboardError("v2_policy_version_mismatch")
    closed_candle_time = report.get("closed_15m_candle_time")
    if isinstance(closed_candle_time, bool) or not isinstance(closed_candle_time, int) or closed_candle_time <= 0:
        raise StrategyV2DashboardError("v2_closed_candle_identity_missing")
    final_gate_version = report.get("final_gate_version")
    gate_pipeline_version = report.get("gate_pipeline_version")
    if not isinstance(final_gate_version, str) or not final_gate_version or not isinstance(gate_pipeline_version, str) or not gate_pipeline_version:
        raise StrategyV2DashboardError("v2_gate_version_missing")
    updated = _timestamp(report.get("updated_at"))
    age = (current - updated).total_seconds()
    if age < -5 or age > max_age_seconds:
        raise StrategyV2DashboardError("v2_report_stale_or_future")
    if report.get("execution_enabled") is not False or report.get("orders_placed") is not False:
        raise StrategyV2DashboardError("v2_execution_boundary_violation")
    if report.get("directional_candidates_blocked_until_gates_approved") is not True:
        raise StrategyV2DashboardError("v2_directional_gate_not_locked")
    gate = report.get("latest_gate_evidence")
    if not isinstance(gate, dict) or gate.get("source") != EXPECTED_SOURCE or gate.get("final_decision") != "NO_TRADE":
        raise StrategyV2DashboardError("v2_latest_gate_evidence_invalid")
    market_data_provenance = _validated_market_data_provenance(report, gate, closed_candle_time)
    entry_context = gate.get("entry_context")
    paper_valid, paper_reason = verify_entry_context(
        entry_context, gate_evidence=gate, now_s=int(current.timestamp())
    )
    paper_setup = {
        "validated": paper_valid,
        "direction": entry_context.get("direction") if paper_valid else "NONE",
        "context": entry_context if paper_valid else None,
        "reason_code": paper_reason,
        "execution_enabled": False,
        "orders_placed": False,
    }
    counts = {}
    for key in ("active_candidates", "wins", "losses", "timeouts"):
        value = report.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise StrategyV2DashboardError("v2_invalid_" + key)
        counts[key] = value
    journal_file = Path(journal_path or os.environ.get("HES_TRADE_JOURNAL_PATH", str(DEFAULT_JOURNAL_PATH)))
    try:
        journal = read_decision_journal(
            journal_file,
            limit=journal_limit,
            now=current,
            expected_source=EXPECTED_SOURCE,
            expected_symbol=EXPECTED_SYMBOL,
            expected_policy_version=EXPECTED_POLICY_VERSION,
            require_execution_off=True,
        )
    except JournalProjectionError as exc:
        raise StrategyV2DashboardError("canonical_journal_invalid:" + str(exc)) from exc
    structure = gate.get("structure")
    if not isinstance(structure, dict):
        raise StrategyV2DashboardError("v2_market_structure_evidence_missing")
    market_observed_at = _timestamp(structure.get("observed_at"))
    market_age = (current - market_observed_at).total_seconds()
    if market_age < -5 or market_age > max_age_seconds:
        raise StrategyV2DashboardError("v2_market_evidence_stale_or_future")
    return {
        "schema": "hes.strategy_v2_dashboard_view.v1", "status": "VERIFIED",
        "agent_version": version, "source": EXPECTED_SOURCE, "symbol": EXPECTED_SYMBOL,
        "timeframe": "15m", "updated_at": updated.isoformat(),
        "closed_15m_candle_time": closed_candle_time,
        "final_gate_version": final_gate_version,
        "gate_pipeline_version": gate_pipeline_version,
        "report_age_seconds": round(max(0.0, age), 3),
        "market_evidence_observed_at": market_observed_at.isoformat(),
        "market_evidence_age_seconds": round(max(0.0, market_age), 3),
        "report_sha256": sha256(raw).hexdigest(),
        "decision": "NO_TRADE", "direction": "NONE",
        "market_regime": structure.get("regime", "UNKNOWN") if isinstance(structure, dict) else "UNKNOWN",
        **counts, "resolved_win_rate_pct": report.get("resolved_win_rate_pct"),
        "target_policy_status": report.get("target_policy_status", "UNKNOWN"),
        "directional_candidates_blocked_until_gates_approved": True,
        "latest_gate_evidence": gate, "market_data_provenance": market_data_provenance, "paper_setup": paper_setup, "journal": journal,
        "execution_enabled": False, "orders_placed": False, "outcomes_inferred": False,
    }
