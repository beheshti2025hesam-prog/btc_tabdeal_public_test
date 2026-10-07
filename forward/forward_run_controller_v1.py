"""Forward Run Controller v1.

Orchestrates one fail-closed forward evaluation cycle without live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .activation_gate_v1 import validate_activation


@dataclass(frozen=True)
class ForwardRunResult:
    run_id: str
    status: str
    decision_count: int
    errors: tuple[str, ...]


class ForwardRunControllerV1:
    def __init__(self, *, policy: Mapping[str, Any], ruleset: Mapping[str, Any]) -> None:
        self.policy = policy
        self.ruleset = ruleset

    def start(self, *, run_id: str, observed_at: datetime, inputs: Sequence[Mapping[str, Any]]) -> ForwardRunResult:
        errors: list[str] = []

        if not run_id or run_id == "FORWARD_RUN_PENDING":
            errors.append("INVALID_RUN_ID")

        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            errors.append("OBSERVED_AT_MUST_BE_TIMEZONE_AWARE")

        activation = validate_activation(self.policy, self.ruleset)
        errors.extend(activation.errors)

        # This controller intentionally does not execute decisions while the
        # policy/ruleset are not active. It also never turns raw inputs into
        # trades by itself.
        if errors:
            return ForwardRunResult(run_id=run_id, status="REJECTED", decision_count=0, errors=tuple(errors))

        return ForwardRunResult(
            run_id=run_id,
            status="READY",
            decision_count=0,
            errors=(),
        )
