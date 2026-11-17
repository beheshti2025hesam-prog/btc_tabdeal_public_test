"""Resolve the exact immutable 15m setup context for the 1m precision engine."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from forward.strategy_entry_context_v1 import verify_entry_context


def resolve_precision_setup_context(
    *,
    setup_rows: Sequence[Mapping[str, Any]],
    strategy_view: Mapping[str, Any],
    now_s: int,
) -> tuple[dict[str, Any] | None, str]:
    """Return the exact context stored with its originating 15m candidate.

    The dashboard's latest gate can be re-evaluated several times while a 15m
    candle remains current. Its dynamic evidence hash must not replace the
    immutable context attached to the original candidate. We therefore match
    the candidate by the exact closed 15m candle and require current gate state
    and evaluator-run identity to remain compatible before allowing 1m timing.
    """
    candle_time = strategy_view.get("closed_15m_candle_time")
    latest_gate = strategy_view.get("latest_gate_evidence")
    if type(candle_time) is not int or candle_time <= 0 or not isinstance(latest_gate, Mapping):
        return None, "CURRENT_STRATEGY_SNAPSHOT_INVALID"

    matches = [
        row for row in setup_rows
        if isinstance(row, Mapping)
        and row.get("candidate_time") == candle_time
        and row.get("source") == "gateio_public_spot"
        and row.get("symbol") == "BTC_USDT"
        and row.get("preapproval_paper_eligible") is True
        and isinstance(row.get("entry_context"), dict)
        and isinstance(row.get("gate_evidence"), dict)
    ]
    if not matches:
        return None, "IMMUTABLE_15M_SETUP_NOT_FOUND"
    if len(matches) != 1:
        return None, "AMBIGUOUS_IMMUTABLE_15M_SETUP"

    row = matches[0]
    if row.get("final_gate_decision") != "NO_TRADE":
        return None, "FINAL_POLICY_GATE_NOT_CLOSED"
    context = row["entry_context"]
    source_gate = row["gate_evidence"]
    if row.get("candidate_event_id") != f"hes-v2-candidate-BTC_USDT-15m-{candle_time}":
        return None, "IMMUTABLE_15M_SETUP_IDENTITY_MISMATCH"

    valid, reason = verify_entry_context(
        context, gate_evidence=source_gate, now_s=now_s
    )
    if not valid:
        return None, "IMMUTABLE_15M_SETUP_CONTEXT_INVALID:" + str(reason)

    direction = context.get("direction")
    expected_confirmation = "CONFIRMED_" + str(direction)
    current_risk = latest_gate.get("risk")
    current_confirmation = latest_gate.get("confirmation")
    current_structure = latest_gate.get("structure")
    if not isinstance(current_risk, Mapping) or current_risk.get("state") != "RISK_APPROVED":
        return None, "CURRENT_RISK_GATE_NOT_APPROVED"
    if not isinstance(current_confirmation, Mapping) or current_confirmation.get("state") != expected_confirmation:
        return None, "CURRENT_CONFIRMATION_NOT_VALID"
    if (
        not isinstance(current_structure, Mapping)
        or current_structure.get("status") != "OBSERVED"
        or current_structure.get("regime") != context.get("market_regime")
    ):
        return None, "CURRENT_STRUCTURE_NOT_ALIGNED"

    context_run = context.get("strategy_run_provenance")
    source_run = source_gate.get("strategy_run_provenance")
    current_run = latest_gate.get("strategy_run_provenance")
    if not isinstance(context_run, Mapping) or not isinstance(source_run, Mapping) or not isinstance(current_run, Mapping):
        return None, "STRATEGY_RUN_PROVENANCE_MISSING"
    for key in ("run_id", "code_release_id", "run_manifest_sha256"):
        expected = context_run.get(key)
        if not isinstance(expected, str) or not expected or source_run.get(key) != expected or current_run.get(key) != expected:
            return None, "STRATEGY_RUN_PROVENANCE_MISMATCH"

    return dict(context), "EXACT_IMMUTABLE_15M_SETUP_LINKED"
