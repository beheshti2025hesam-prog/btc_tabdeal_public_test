"""Independent verifier for serialized Mother Orchestrator audit output.

This module verifies the published audit envelope only. It does not run agents,
fetch market data, recalculate strategy, alter decisions, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUIRED_STAGES = (
    "data_quality",
    "market_structure",
    "signal",
    "confirmation",
    "risk",
    "decision",
    "evaluation",
)
_ALLOWED_STATES = {
    "data_quality": {"PASS"},
    "market_structure": {"PASS"},
    "signal": {"PASS"},
    "confirmation": {"CONFIRMED"},
    "risk": {"APPROVED"},
    "decision": {"DECIDED"},
    "evaluation": {"OBSERVED"},
}
_DECISIONS = {"LONG", "SHORT", "NO_TRADE"}


@dataclass(frozen=True)
class WitnessResultV1:
    verified: bool
    reason_codes: tuple[str, ...]
    trace_id: str = ""
    audit_sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "hes.mother_witness.v1",
            "verified": self.verified,
            "reason_codes": list(self.reason_codes),
            "trace_id": self.trace_id,
            "audit_sha256": self.audit_sha256,
            "execution_authorized": False,
        }


class MotherAuditWitnessV1:
    """Verify audit digest and safety invariants without trusting its producer."""

    VERSION = "hes-mother-orchestrator-v1"

    @staticmethod
    def _fail(*reasons: str) -> WitnessResultV1:
        return WitnessResultV1(False, tuple(reasons))

    def verify(self, envelope: Any) -> WitnessResultV1:
        if not isinstance(envelope, Mapping):
            return self._fail("WITNESS_ENVELOPE_NOT_MAPPING")
        trace_id = envelope.get("trace_id", "")
        digest = envelope.get("audit_sha256", "")
        status = envelope.get("status")
        decision = envelope.get("decision")
        reasons = envelope.get("reason_codes")
        stages = envelope.get("stages")
        if envelope.get("schema_version") != "hes.mother_orchestration.v1":
            return self._fail("WITNESS_SCHEMA_VERSION_INVALID")
        if envelope.get("execution_authorized") is not False:
            return self._fail("WITNESS_EXECUTION_BOUNDARY_VIOLATION")
        if not isinstance(trace_id, str) or not _SHA256.fullmatch(trace_id):
            return self._fail("WITNESS_TRACE_ID_INVALID")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            return self._fail("WITNESS_AUDIT_HASH_INVALID")
        if not isinstance(status, str) or not status:
            return self._fail("WITNESS_STATUS_INVALID")
        if decision not in _DECISIONS:
            return self._fail("WITNESS_DECISION_INVALID")
        if not isinstance(reasons, list) or any(not isinstance(x, str) or not x for x in reasons):
            return self._fail("WITNESS_REASON_CODES_INVALID")
        if len(reasons) != len(set(reasons)):
            return self._fail("WITNESS_REASON_CODES_DUPLICATED")
        if not isinstance(stages, list) or len(stages) > len(_REQUIRED_STAGES):
            return self._fail("WITNESS_STAGES_INVALID")
        names = [stage.get("agent") if isinstance(stage, Mapping) else None for stage in stages]
        if tuple(names) != _REQUIRED_STAGES[:len(names)]:
            return self._fail("WITNESS_STAGE_ORDER_INVALID")
        observation = status == "OBSERVATION_ONLY"
        if observation and len(names) != len(_REQUIRED_STAGES):
            return self._fail("WITNESS_OBSERVATION_CHAIN_INCOMPLETE")
        if not observation and (not status.startswith("BLOCKED_") or decision != "NO_TRADE"):
            return self._fail("WITNESS_BLOCKED_DECISION_NOT_NO_TRADE")

        audit_rows: list[dict[str, Any]] = []
        for index, (name, stage) in enumerate(zip(names, stages)):
            if not isinstance(stage, Mapping):
                return self._fail("WITNESS_STAGE_INVALID:" + str(name))
            version = stage.get("agent_version")
            state = stage.get("state")
            if not isinstance(version, str) or not version.strip():
                return self._fail("WITNESS_AGENT_VERSION_INVALID:" + name)
            if not isinstance(state, str) or not state.strip():
                return self._fail("WITNESS_STAGE_STATE_INVALID:" + name)
            if observation and state not in _ALLOWED_STATES[name]:
                return self._fail("WITNESS_STAGE_STATE_INVALID:" + name)
            stage_reasons = stage.get("reason_codes")
            refs = stage.get("evidence_refs")
            if not isinstance(stage_reasons, list) or any(not isinstance(x, str) or not x for x in stage_reasons):
                return self._fail("WITNESS_STAGE_REASONS_INVALID:" + name)
            if len(stage_reasons) != len(set(stage_reasons)):
                return self._fail("WITNESS_STAGE_REASONS_DUPLICATED:" + name)
            if not isinstance(refs, list) or any(not isinstance(x, str) or not x for x in refs):
                return self._fail("WITNESS_STAGE_EVIDENCE_INVALID:" + name)
            if len(refs) != len(set(refs)):
                return self._fail("WITNESS_STAGE_EVIDENCE_DUPLICATED:" + name)
            row_decision = stage.get("decision") if name == "decision" else None
            if name == "decision":
                if observation and row_decision != decision:
                    return self._fail("WITNESS_DECISION_STAGE_MISMATCH")
                if not observation and row_decision not in (*_DECISIONS, "INVALID"):
                    return self._fail("WITNESS_BLOCKED_STAGE_DECISION_INVALID")
            audit_rows.append({
                "agent": name,
                "agent_version": version,
                "state": state,
                "reason_codes": stage_reasons,
                "evidence_refs": refs,
                "decision": row_decision,
            })
        if observation and "EXECUTION_NOT_AUTHORIZED" not in reasons:
            return self._fail("WITNESS_OBSERVATION_BOUNDARY_MISSING")

        audit = {
            "version": self.VERSION,
            "trace_id": trace_id,
            "status": status,
            "decision": decision,
            "reason_codes": reasons,
            "stages": audit_rows,
            "execution_authorized": False,
        }
        try:
            actual = sha256(json.dumps(
                audit, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode()).hexdigest()
        except (TypeError, ValueError):
            return self._fail("WITNESS_AUDIT_NOT_CANONICAL_JSON")
        if actual != digest:
            return self._fail("WITNESS_AUDIT_DIGEST_MISMATCH")
        return WitnessResultV1(True, ("WITNESS_VERIFIED",), trace_id, digest)
