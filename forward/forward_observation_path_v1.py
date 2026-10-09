"""End-to-end forward observation path.

Tabdeal read-only frame -> sequence -> closed candle -> structure -> regime
-> quality -> deterministic snapshot -> append-only journal.

Observation-only and fail-closed: no signals, trades, execution, historical
evidence, or future outcomes.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from itertools import islice

from .tabdeal_readonly_adapter_v1 import parse_trade_frame
from .sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1
from .clean_structure_context_v1 import CleanStructureContextV1
from .clean_structure_stability_v1 import CleanStructureStabilityV1
from .clean_regime_observation_v1 import CleanRegimeObservationV1
from .clean_regime_quality_v1 import CleanRegimeQualityV1
from .clean_regime_quality_gate_v1 import CleanRegimeQualityGateV1
from .observation_journal_v1 import ObservationJournalV1
from .observation_journal_integration_v1 import ObservationJournalIntegrationV1

@dataclass(frozen=True)
class ForwardObservationPathResult:
    status: str
    forward_run_id: str
    frames_accepted: int
    candles: int
    gaps: int
    structure_bias: str | None
    regime: str | None
    quality: str | None
    gate_safe: bool
    snapshot_id: str | None
    reason: str
    diagnostics: tuple[dict[str, Any], ...] = ()

class ForwardObservationPathV1:
    def __init__(self, journal_path: str | Path, *, max_records: int = 100_000):
        if max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.journal = ObservationJournalV1(journal_path)
        self.writer = ObservationJournalIntegrationV1(self.journal)

    @staticmethod
    def _candle_payload(c: Any) -> dict[str, Any]:
        return {"symbol": c.symbol, "timeframe": c.timeframe,
                "open_time": c.open_time.astimezone(timezone.utc).isoformat(),
                "close_time": c.close_time.astimezone(timezone.utc).isoformat(),
                "open": str(c.open), "high": str(c.high), "low": str(c.low),
                "close": str(c.close), "volume": str(c.volume),
                "trade_count": c.trade_count, "first_sequence": c.first_sequence,
                "last_sequence": c.last_sequence}

    def observe(self, frames: Iterable[dict[str, Any]], *, as_of: datetime,
                forward_run_id: str) -> ForwardObservationPathResult:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if not forward_run_id.strip():
            raise ValueError("forward_run_id required")

        bounded_frames = list(islice(frames, self.max_records + 1))
        if len(bounded_frames) > self.max_records:
            return ForwardObservationPathResult(
                "BLOCKED", forward_run_id, 0, 0, 0, None, None, None,
                False, None, "FORWARD_RECORD_BOUND_EXCEEDED",
                ({"max_records": self.max_records},),
            )
        parsed = [parse_trade_frame(frame, as_of=as_of) for frame in bounded_frames]
        result = SequenceAwareCandleIngestionV1(max_sequence_records=self.max_records).ingest(parsed, as_of=as_of)
        if not result.safe_for_decision:
            return ForwardObservationPathResult("BLOCKED", forward_run_id, len(parsed), 0, 0,
                                                None, None, None, False, None, "SEQUENCE_UNSAFE",
                                                tuple({
                                                    "sequence": e.sequence,
                                                    "status": e.status,
                                                    "reason": e.reason,
                                                    **({"diagnostic": e.diagnostic} if e.diagnostic is not None else {}),
                                                } for e in result.events))
        if result.gaps:
            return ForwardObservationPathResult("BLOCKED", forward_run_id, len(parsed),
                                                len(result.candles), len(result.gaps),
                                                None, None, None, False, None, "CANDLE_INTERVAL_GAP")
        if len(result.candles) < 2:
            return ForwardObservationPathResult("WAITING", forward_run_id, len(parsed),
                                                len(result.candles), 0, None, None, None,
                                                False, None, "INSUFFICIENT_CLOSED_CANDLES")

        candle_dicts = [{"symbol": c.symbol, "timeframe": c.timeframe,
                         "status": "CANDLE_CLOSED_OBSERVED", "open": str(c.open),
                         "high": str(c.high), "low": str(c.low), "close": str(c.close)}
                        for c in result.candles]
        contexts = [CleanStructureContextV1().observe(candle_dicts[:i+1])
                    for i in range(1, len(candle_dicts))]
        stability = CleanStructureStabilityV1().observe([c.bias for c in contexts])
        regime = CleanRegimeObservationV1().observe(stability.stable_bias)
        if regime.regime == "UPTREND":
            persistence = stability.up_contexts / stability.observations
        elif regime.regime == "DOWNTREND":
            persistence = stability.down_contexts / stability.observations
        else:
            persistence = 0.0
        quality = CleanRegimeQualityV1().observe(regime=regime.regime,
                                                  persistence_ratio=persistence,
                                                  transition="NO_CHANGE")
        gate = CleanRegimeQualityGateV1().evaluate(quality.quality)
        payload = {
            "sequence_events": [{"sequence": e.sequence, "status": e.status, "reason": e.reason}
                                for e in result.events],
            "candles": [self._candle_payload(c) for c in result.candles],
            "structure": {"contexts": [c.bias for c in contexts],
                          "stable_bias": stability.stable_bias,
                          "observations": stability.observations},
            "regime": {"value": regime.regime, "confidence_state": regime.confidence_state},
            "quality": {"value": quality.quality, "reason": quality.reason},
            "gate": {"safe_for_observation": gate.safe_for_observation, "reason": gate.reason},
        }
        report, snapshot = self.writer.record(
            forward_run_id=forward_run_id,
            observed_at=as_of.astimezone(timezone.utc),
            regime=regime.regime,
            quality=quality.quality,
            gate_safe=gate.safe_for_observation,
            observation_payload=payload,
        )
        return ForwardObservationPathResult("OBSERVED", forward_run_id, len(parsed),
                                            len(result.candles), 0, contexts[-1].bias,
                                            regime.regime, quality.quality,
                                            gate.safe_for_observation, snapshot.snapshot_id,
                                            report.report_state)
