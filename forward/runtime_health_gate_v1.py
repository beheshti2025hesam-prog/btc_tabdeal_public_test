"""Pure runtime-health classification for bounded forward observations.

This module does not alter observation semantics, sequence rules, evidence,
persistence, execution, or trading decisions. It classifies an already
completed runner result so operational health is distinguishable from
data-safety blocking.
"""
from __future__ import annotations

from dataclasses import dataclass

from .controlled_forward_observation_runner_v1 import (
    ControlledObservationRunnerResult,
)


@dataclass(frozen=True)
class ForwardRuntimeHealthResult:
    health: str
    source_status: str
    source_reason: str
    records_received: int
    observation_safe: bool
    diagnostics_count: int


class ForwardRuntimeHealthGateV1:
    """Classify an existing runner result without changing its semantics."""

    @staticmethod
    def evaluate(
        result: ControlledObservationRunnerResult,
    ) -> ForwardRuntimeHealthResult:
        if result.status == "WAITING":
            health = "WAITING"
        elif result.status == "BLOCKED":
            health = (
                "TRANSPORT_ERROR"
                if result.reason.startswith("TRANSPORT_ERROR:")
                else "BLOCKED"
            )
        elif result.status == "OBSERVED":
            health = "HEALTHY"
        else:
            raise ValueError(f"unknown runner status: {result.status}")

        return ForwardRuntimeHealthResult(
            health=health,
            source_status=result.status,
            source_reason=result.reason,
            records_received=result.records_received,
            observation_safe=(
                result.status == "OBSERVED"
                and result.snapshot_id is not None
            ),
            diagnostics_count=len(result.diagnostics),
        )
