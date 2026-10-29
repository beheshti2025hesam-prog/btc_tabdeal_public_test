"""Bridge Signal Agent decisions into the existing forward-evidence journal.

Realized outcomes remain separate immutable JSON artifacts consumed by the
existing build_report_from_forward_evidence reader. This module does not invent
an outcome format, infer results, tune policy, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable

from .forward_observation_writer_v1 import (
    ForwardObservationWriterV1,
    observation_digest,
)
from .learning_loop_v1 import ForwardEvidenceRun, build_report_from_forward_evidence
from .runtime_guard_v1 import RuntimeContext


@dataclass(frozen=True)
class JournalWriteResult:
    status: str
    event_id: str
    digest: str


def record_signal_decision(
    journal_path: str | Path,
    *,
    decision: str,
    observed_at: str,
    symbol: str,
    timeframe: str,
    source: str,
    product: str,
    response_sha256: str,
    htf_response_sha256: str,
    strategy_evidence_sha256: str | None,
    policy_version: str,
    status: str,
    market_regime: str,
    rejected_at: str,
    reason_codes: Iterable[str],
) -> JournalWriteResult:
    """Persist an idempotent, immutable decision observation with no outcome."""
    if not isinstance(decision, str) or decision not in {"LONG", "SHORT", "NO_TRADE"}:
        raise ValueError("invalid_decision")
    for name, value in (
        ("observed_at", observed_at), ("symbol", symbol), ("timeframe", timeframe),
        ("source", source), ("product", product), ("policy_version", policy_version),
        ("status", status), ("market_regime", market_regime),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("invalid_" + name)
    if not isinstance(rejected_at, str):
        raise ValueError("invalid_rejected_at")
    for name, value in (
        ("response_sha256", response_sha256),
        ("htf_response_sha256", htf_response_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("invalid_" + name)
    if strategy_evidence_sha256 is not None and (
        not isinstance(strategy_evidence_sha256, str) or len(strategy_evidence_sha256) != 64
        or any(c not in "0123456789abcdef" for c in strategy_evidence_sha256)
    ):
        raise ValueError("invalid_strategy_evidence_sha256")
    if isinstance(reason_codes, (str, bytes)):
        raise ValueError("invalid_reason_codes")
    reasons = list(reason_codes)
    if any(not isinstance(reason, str) or not reason.strip() for reason in reasons):
        raise ValueError("invalid_reason_codes")

    # Identity is based on immutable inputs and policy version, not the output.
    # A changed decision for identical evidence is a conflict, never a new sample.
    # Polling the same immutable candle batches must not create a new event every
    # refresh. Identity is source/scope/policy based; observed_at and the provider's
    # volatile evidence digest are retained in the first record but not in its key.
    identity = {
        "symbol": symbol, "timeframe": timeframe,
        "source": source, "product": product, "response_sha256": response_sha256,
        "htf_response_sha256": htf_response_sha256,
        "policy_version": policy_version,
    }
    identity_sha = sha256(json.dumps(
        identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")).hexdigest()
    run_id = "signal-" + identity_sha
    event_id = run_id + ":decision"
    no_trade_reason = ";".join(reasons) if decision == "NO_TRADE" and reasons else (
        "NO_TRADE_GATED" if decision == "NO_TRADE" else None
    )
    payload = {
        "event_id": event_id,
        "observed_at": observed_at,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": status,
        "source": source,
        "evidence_source": f"{source}:15m={response_sha256}:4h={htf_response_sha256}",
        "product": product,
        "artifact_kind": "SIGNAL_DECISION",
        "decision": decision,
        "no_trade_reason": no_trade_reason,
        "market_regime": market_regime,
        "decision_gate": rejected_at or "SIGNAL_AGENT",
        "rejected_at": rejected_at,
        "reason_codes": reasons,
        "response_sha256": response_sha256,
        "htf_response_sha256": htf_response_sha256,
        "strategy_evidence_sha256": strategy_evidence_sha256,
        "policy_version": policy_version,
        "source_period": "forward",
        "population": "forward",
        "execution": "OFF",
    }
    context = RuntimeContext(source=source, observed_at=observed_at, forward_run_id=run_id)
    try:
        digest = ForwardObservationWriterV1(journal_path).append(payload, context=context)
        return JournalWriteResult("RECORDED", event_id, digest)
    except ValueError as exc:
        if "duplicate observation event_id" not in str(exc):
            raise
        expected_payload = {**payload, "artifact_type": "FORWARD_OBSERVATION", "artifact_version": "1.0"}
        expected = observation_digest(expected_payload)
        for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            if existing.get("event_id") == event_id:
                if existing.get("digest") == expected:
                    return JournalWriteResult("ALREADY_RECORDED", event_id, expected)
                # The evaluation timestamp/evidence digest may differ on a repeated
                # poll even when the source batches and policy are identical. Treat
                # that as the same observation only if every decision-relevant field
                # is unchanged; any changed decision/gate/reason remains a conflict.
                comparable_existing = dict(existing)
                comparable_expected = dict(expected_payload)
                for volatile in ("digest", "observed_at", "strategy_evidence_sha256"):
                    comparable_existing.pop(volatile, None)
                    comparable_expected.pop(volatile, None)
                if comparable_existing == comparable_expected:
                    return JournalWriteResult("ALREADY_RECORDED", event_id, existing.get("digest", expected))
                raise ValueError("conflicting_duplicate_decision_event")
        raise


def build_forward_learning_report(
    journal_path: str | Path,
    outcome_dir: str | Path,
    *,
    now=None,
    min_group_size: int = 5,
) -> ForwardEvidenceRun:
    """Delegate to the existing strict reader and immutable outcome contract."""
    return build_report_from_forward_evidence(
        journal_path, outcome_dir, now=now, min_group_size=min_group_size
    )
