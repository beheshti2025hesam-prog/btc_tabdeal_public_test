"""Live, read-only Mother dashboard backed by the seven runtime specialists.

Unlike the legacy report projection, this path loads the current validated
Gate.io candle ledger and invokes the existing HES evaluators on every request.
It never uses a pre-generated Strategy V2 report as a specialist result.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json

from core.orchestration.mother_v1 import MotherOrchestratorV1
from core.orchestration.mother_runtime_specialists_v1 import (
    LiveMarketContextV1,
    live_specialists_v1,
    specialist_registry_v1,
)
from core.orchestration.witness_v1 import MotherAuditWitnessV1

SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"


class MotherRuntimeDashboardError(ValueError):
    """The live Mother runtime could not produce a verifiable observation."""


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def read_mother_runtime_dashboard(
    *,
    data_root: str | Path = "/opt/hes-trade-agent",
    journal_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise MotherRuntimeDashboardError("MOTHER_RUNTIME_CLOCK_NOT_TIMEZONE_AWARE")
    observed = observed.astimezone(timezone.utc)
    market = LiveMarketContextV1(data_root=data_root, observed_at=observed, journal_path=journal_path)

    # Load the canonical persisted market input once. Every specialist below
    # shares this memoized snapshot; no specialist makes a second REST request.
    try:
        market.load()
    except Exception:
        # The data-quality specialist will re-surface the failure as a blocked
        # stage; hashes remain valid so the independent witness can verify it.
        pass

    snapshot_sha = market.snapshot_sha256 or _canonical_hash({
        "source": SOURCE, "symbol": SYMBOL, "observed_at": observed.isoformat(),
    })
    registry = specialist_registry_v1()
    evidence_sha = _canonical_hash({
        "snapshot_sha256": snapshot_sha,
        "specialist_registry": registry,
        "runtime_mode": "LIVE_DATA_RUNTIME_SPECIALISTS",
    })
    request_id = "hes-mother-live-" + observed.strftime("%Y%m%dT%H%M%S") + "-" + snapshot_sha[:16]
    context = {
        "scope": {"venue": "gateio", "product": "spot", "symbol": SYMBOL, "timeframe": "15m"},
        "observed_at": observed.isoformat(),
        "snapshot_sha256": snapshot_sha,
        "evidence_sha256": evidence_sha,
        "request_id": request_id,
    }
    result = MotherOrchestratorV1(live_specialists_v1(market)).run(context)
    envelope = result.as_dict()
    witness = MotherAuditWitnessV1().verify(envelope)
    if not witness.verified:
        raise MotherRuntimeDashboardError("MOTHER_RUNTIME_WITNESS_REJECTED:" + "|".join(witness.reason_codes))

    summary = market.summary()
    stages = envelope["stages"]
    return {
        "schema": "hes.mother_runtime_dashboard.v1",
        "runtime_mode": "LIVE_DATA_RUNTIME_SPECIALISTS",
        "status": result.status,
        "decision": result.decision,
        "reason_codes": list(result.reason_codes),
        "trace_id": result.trace_id,
        "audit_sha256": result.audit_sha256,
        "source": SOURCE,
        "symbol": SYMBOL,
        "timeframe": "15m",
        "observed_at": observed.isoformat(),
        "request_id": request_id,
        "snapshot_sha256": snapshot_sha,
        "market_data_provenance": summary.get("market_data_provenance"),
        "market_regime": summary.get("market_regime", "UNKNOWN"),
        "strategy_proposal": summary.get("strategy_proposal"),
        "precision_entry": summary.get("precision_entry"),
        "recovery_evidence": summary.get("recovery_evidence"),
        "paper_execution_gate": summary.get("paper_execution_gate"),
        "sequence_validation": summary.get("sequence_validation"),
        "registered_specialists": registry,
        "executed_specialists": [row["agent"] for row in stages],
        "registered_count": len(registry),
        "executed_count": len(stages),
        "stages": stages,
        "witness": witness.as_dict(),
        "execution_authorized": False,
        "execution_enabled": False,
        "orders_placed": False,
        "journal_write": False,
        "outcomes_inferred": False,
        "external_llm_used": False,
    }
