"""Deterministic release-readiness gate for forward-only changes."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    reason: str

class ReleaseReadinessGateV1:
    REQUIRED = (
        "tests_pass",
        "contracts_present",
        "safety_invariants_pass",
        "historical_firewall_pass",
        "execution_locked",
        "collector_disabled",
        "git_integrity_pass",
        "upstream_sequence_contract_verified",
    )
    def evaluate(self, **checks: bool) -> ReadinessResult:
        for name in self.REQUIRED:
            if checks.get(name) is not True:
                return ReadinessResult(False, name)
        return ReadinessResult(True, "READY")
