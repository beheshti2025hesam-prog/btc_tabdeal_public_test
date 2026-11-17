"""Independent verifier for serialized Mother Orchestrator audit output.

This module verifies the published audit envelope only. It does not run agents,
fetch market data, recalculate strategy, alter decisions, or authorize execution.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
_DIRECTIONS = {"LONG", "SHORT", "NEUTRAL", "UNKNOWN"}
_CONSENSUS_AGENTS = {"data_quality", "market_structure", "strategy", "confirmation", "risk"}


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
        consensus = envelope.get("consensus")
        if "consensus" not in envelope:
            return self._fail("WITNESS_CONSENSUS_MISSING")
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
            if not refs:
                return self._fail("WITNESS_STAGE_EVIDENCE_MISSING:" + name)
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
        if consensus is None:
            if len(names) == len(_REQUIRED_STAGES):
                return self._fail("WITNESS_CONSENSUS_MISSING")
        else:
            if not isinstance(consensus, Mapping):
                return self._fail("WITNESS_CONSENSUS_INVALID")
            resolver_version = consensus.get("resolver_version")
            c_decision = consensus.get("decision")
            c_direction = consensus.get("direction")
            c_class = consensus.get("conflict_class")
            c_reasons = consensus.get("reason_codes")
            c_assessments = consensus.get("assessments")
            c_digest = consensus.get("audit_sha256")
            if resolver_version != "hes-agent-disagreement-resolver-v1":
                return self._fail("WITNESS_CONSENSUS_VERSION_INVALID")
            if c_decision not in _DECISIONS or c_direction not in _DIRECTIONS:
                return self._fail("WITNESS_CONSENSUS_DECISION_INVALID")
            if not isinstance(c_class, str) or not c_class:
                return self._fail("WITNESS_CONSENSUS_CLASS_INVALID")
            if not isinstance(c_reasons, list) or any(not isinstance(x, str) or not x for x in c_reasons):
                return self._fail("WITNESS_CONSENSUS_REASONS_INVALID")
            if c_reasons != sorted(set(c_reasons)):
                return self._fail("WITNESS_CONSENSUS_REASONS_NONCANONICAL")
            if not isinstance(c_assessments, list) or len(c_assessments) != len(_CONSENSUS_AGENTS):
                return self._fail("WITNESS_CONSENSUS_ASSESSMENTS_INVALID")
            if not isinstance(c_digest, str) or not _SHA256.fullmatch(c_digest):
                return self._fail("WITNESS_CONSENSUS_HASH_INVALID")
            agent_ids = []
            scopes = set()
            snapshots = set()
            timestamps = set()
            for row in c_assessments:
                if not isinstance(row, Mapping):
                    return self._fail("WITNESS_CONSENSUS_ASSESSMENT_INVALID")
                agent_id = row.get("agent_id")
                agent_version = row.get("agent_version")
                state = row.get("state")
                direction = row.get("direction")
                scope = row.get("scope")
                as_of = row.get("as_of")
                snapshot_hash = row.get("snapshot_sha256")
                evidence_hash = row.get("evidence_sha256")
                row_reasons = row.get("reason_codes")
                if not isinstance(agent_id, str) or not agent_id or agent_id in agent_ids:
                    return self._fail("WITNESS_CONSENSUS_AGENT_INVALID")
                if not isinstance(agent_version, str) or not agent_version:
                    return self._fail("WITNESS_CONSENSUS_AGENT_VERSION_INVALID")
                if state not in {"PASS", "FAIL", "UNKNOWN"} or direction not in _DIRECTIONS:
                    return self._fail("WITNESS_CONSENSUS_ASSESSMENT_STATE_INVALID")
                if not isinstance(scope, list) or len(scope) != 4 or any(not isinstance(x, str) or not x for x in scope):
                    return self._fail("WITNESS_CONSENSUS_SCOPE_INVALID")
                if not isinstance(as_of, str) or not as_of:
                    return self._fail("WITNESS_CONSENSUS_TIMESTAMP_INVALID")
                try:
                    parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
                except ValueError:
                    return self._fail("WITNESS_CONSENSUS_TIMESTAMP_INVALID")
                if parsed_as_of.tzinfo is None or parsed_as_of.utcoffset() is None:
                    return self._fail("WITNESS_CONSENSUS_TIMESTAMP_INVALID")
                if not isinstance(snapshot_hash, str) or not _SHA256.fullmatch(snapshot_hash):
                    return self._fail("WITNESS_CONSENSUS_SNAPSHOT_HASH_INVALID")
                if not isinstance(evidence_hash, str) or not _SHA256.fullmatch(evidence_hash):
                    return self._fail("WITNESS_CONSENSUS_EVIDENCE_HASH_INVALID")
                if not isinstance(row_reasons, list) or any(not isinstance(x, str) or not x for x in row_reasons):
                    return self._fail("WITNESS_CONSENSUS_ASSESSMENT_REASONS_INVALID")
                if row_reasons != sorted(set(row_reasons)):
                    return self._fail("WITNESS_CONSENSUS_ASSESSMENT_REASONS_NONCANONICAL")
                agent_ids.append(agent_id)
                scopes.add(tuple(scope))
                snapshots.add(snapshot_hash)
                timestamps.add(as_of)
            if set(agent_ids) != _CONSENSUS_AGENTS or len(scopes) != 1 or len(snapshots) != 1 or len(timestamps) != 1:
                return self._fail("WITNESS_CONSENSUS_SNAPSHOT_COHERENCE_INVALID")
            if c_class == "CONSENSUS":
                if c_decision not in ("LONG", "SHORT") or c_direction != c_decision:
                    return self._fail("WITNESS_CONSENSUS_RESULT_INVALID")
            elif c_decision != "NO_TRADE" or c_direction != "UNKNOWN":
                return self._fail("WITNESS_CONSENSUS_NO_TRADE_INVALID")
            resolver_audit = {
                "resolver_version": resolver_version,
                "decision": c_decision,
                "direction": c_direction,
                "conflict_class": c_class,
                "reason_codes": c_reasons,
                "assessments": c_assessments,
            }
            actual_consensus_digest = sha256(json.dumps(
                resolver_audit, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            if actual_consensus_digest != c_digest:
                return self._fail("WITNESS_CONSENSUS_DIGEST_MISMATCH")

        if observation and "EXECUTION_NOT_AUTHORIZED" not in reasons:
            return self._fail("WITNESS_OBSERVATION_BOUNDARY_MISSING")

        audit = {
            "version": self.VERSION,
            "trace_id": trace_id,
            "status": status,
            "decision": decision,
            "reason_codes": reasons,
            "stages": audit_rows,
            "consensus": consensus,
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
