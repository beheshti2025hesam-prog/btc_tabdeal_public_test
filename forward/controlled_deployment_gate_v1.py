"""Fail-closed preflight and postflight gates for controlled HES releases."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class DeploymentGateResultV1:
    ready: bool
    phase: str
    reason: str

class ControlledDeploymentGateV1:
    PREFLIGHT_REQUIRED = (
        "target_release_manifest_verified",
        "rollback_release_manifest_verified",
        "pointers_snapshot_verified",
        "unit_backup_verified",
        "deployment_lock_acquired",
        "rollback_path_verified",
        "execution_locked",
        "orders_locked",
        "paper_only_invariants_pass",
    )
    POSTFLIGHT_REQUIRED = (
        "all_services_active",
        "learning_report_fresh",
        "operational_healthcheck_pass",
        "stability_window_pass",
    )

    @staticmethod
    def _evaluate(phase: str, required: tuple[str, ...], checks: dict[str, object]) -> DeploymentGateResultV1:
        for name in required:
            if checks.get(name) is not True:
                return DeploymentGateResultV1(False, phase, name)
        return DeploymentGateResultV1(True, phase, "READY")

    def evaluate_preflight(self, **checks: bool) -> DeploymentGateResultV1:
        return self._evaluate("PREFLIGHT", self.PREFLIGHT_REQUIRED, checks)

    def evaluate_postflight(self, **checks: bool) -> DeploymentGateResultV1:
        return self._evaluate("POSTFLIGHT", self.POSTFLIGHT_REQUIRED, checks)
