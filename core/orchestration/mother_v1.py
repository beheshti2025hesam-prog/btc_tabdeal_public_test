"""Bounded, deterministic Mother Orchestrator v1.

This is a control plane over existing specialist outputs, not another market,
strategy, risk, learning, or execution engine. Specialist implementations are
injected; this module validates their order, contracts, provenance, and vetoes.
It never fetches data or submits orders.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Protocol

from core.orchestration.mother_consensus_v1 import resolve_mother_consensus_v1


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_REASON_CODES = 64
_MAX_EVIDENCE_REFS = 128
_MAX_TEXT = 256
_ALLOWED = {
    "data_quality": frozenset({"PASS"}),
    "market_structure": frozenset({"PASS"}),
    "signal": frozenset({"PASS"}),
    "confirmation": frozenset({"CONFIRMED"}),
    "risk": frozenset({"APPROVED"}),
    "decision": frozenset({"DECIDED"}),
    "evaluation": frozenset({"OBSERVED"}),
}


@dataclass(frozen=True)
class AgentResult:
    agent: str
    state: str
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    payload: Any = None
    agent_version: str = ""


@dataclass(frozen=True)
class OrchestrationResult:
    status: str
    decision: str
    stages: tuple[AgentResult, ...]
    reason_codes: tuple[str, ...]
    execution_authorized: bool = False
    schema_version: str = "hes.mother_orchestration.v1"
    trace_id: str = ""
    audit_sha256: str = ""
    consensus: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        rows = []
        for stage in self.stages:
            row: dict[str, Any] = {
                "agent": stage.agent,
                "agent_version": stage.agent_version,
                "state": stage.state,
                "reason_codes": list(stage.reason_codes),
                "evidence_refs": list(stage.evidence_refs),
            }
            if stage.agent == "decision":
                row["decision"] = _safe_decision(_decision_value(stage.payload))
            rows.append(row)
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "execution_authorized": False,
            "trace_id": self.trace_id,
            "audit_sha256": self.audit_sha256,
            "consensus": deepcopy(self.consensus) if self.consensus is not None else None,
            "stages": rows,
        }


class SpecialistAgent(Protocol):
    name: str
    def evaluate(self, context: Mapping[str, Any]) -> AgentResult: ...


def _decision_value(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return payload.get("decision")
    return getattr(payload, "decision", None)


def _utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _safe_decision(value: Any) -> str:
    return value if isinstance(value, str) and value in ("LONG", "SHORT", "NO_TRADE") else "INVALID"


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= _MAX_TEXT and value == value.strip()


class PrecomputedSpecialistV1:
    """Expose an existing validated specialist result without recomputing it."""

    VERSION = "hes-precomputed-specialist-adapter-v1"

    def __init__(self, name: str):
        if name not in _ALLOWED:
            raise ValueError("unregistered specialist name")
        self.name = name

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        reports = context.get("specialist_reports")
        if not isinstance(reports, Mapping):
            return AgentResult(self.name, "UNKNOWN", ("SPECIALIST_REPORTS_MISSING",), (), {}, self.VERSION)
        report = reports.get(self.name)
        if not isinstance(report, Mapping):
            return AgentResult(self.name, "UNKNOWN", ("SPECIALIST_REPORT_MISSING:" + self.name,), (), {}, self.VERSION)
        state = report.get("state")
        reasons = report.get("reason_codes", ())
        refs = report.get("evidence_refs", ())
        payload = report.get("payload", {})
        if not isinstance(reasons, (tuple, list)) or not isinstance(refs, (tuple, list)):
            return AgentResult(self.name, "UNKNOWN", ("SPECIALIST_REPORT_MALFORMED:" + self.name,), (), {}, self.VERSION)
        version = report.get("agent_version")
        return AgentResult(self.name, state, tuple(reasons), tuple(refs), payload, version)


def precomputed_specialists_v1() -> dict[str, PrecomputedSpecialistV1]:
    """Canonical registry for the existing dashboard pipeline's outputs."""
    return {name: PrecomputedSpecialistV1(name) for name in _ALLOWED}


class MotherOrchestratorV1:
    """Run a fixed, bounded specialist sequence; every missing/invalid gate blocks."""

    VERSION = "hes-mother-orchestrator-v1"
    REQUIRED = tuple(_ALLOWED)

    def __init__(self, agents: Mapping[str, SpecialistAgent]):
        if not isinstance(agents, Mapping):
            raise TypeError("agents must be a mapping")
        self.agents = dict(agents)

    @staticmethod
    def _validate_context(context: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(context, Mapping):
            return None, "CONTEXT_NOT_A_MAPPING"
        try:
            safe = deepcopy(dict(context))
        except Exception:
            return None, "CONTEXT_NOT_COPYABLE"
        scope = safe.get("scope")
        if not isinstance(scope, Mapping) or set(scope) != {"venue", "product", "symbol", "timeframe"}:
            return None, "CONTEXT_SCOPE_INVALID"
        if not all(_text(scope.get(key)) for key in ("venue", "product", "symbol", "timeframe")):
            return None, "CONTEXT_SCOPE_INVALID"
        observed_at = _utc(safe.get("observed_at"))
        if observed_at is None:
            return None, "CONTEXT_TIMESTAMP_INVALID"
        if observed_at > datetime.now(timezone.utc):
            return None, "CONTEXT_FUTURE_TIMESTAMP"
        if not _valid_hash(safe.get("snapshot_sha256")) or not _valid_hash(safe.get("evidence_sha256")):
            return None, "CONTEXT_PROVENANCE_INVALID"
        if "request_id" in safe and (not isinstance(safe["request_id"], str) or len(safe["request_id"]) > 256):
            return None, "CONTEXT_REQUEST_ID_INVALID"
        if "specialist_reports" in safe:
            reports = safe["specialist_reports"]
            if not isinstance(reports, Mapping) or set(reports) != set(_ALLOWED):
                return None, "SPECIALIST_REPORT_SET_INVALID"
            try:
                report_bytes = json.dumps(reports, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
            except (TypeError, ValueError):
                return None, "SPECIALIST_REPORTS_NOT_CANONICAL_JSON"
            if sha256(report_bytes).hexdigest() != safe["evidence_sha256"]:
                return None, "SPECIALIST_REPORT_DIGEST_MISMATCH"
        safe["observed_at"] = observed_at.isoformat()
        safe["scope"] = {key: scope[key] for key in ("venue", "product", "symbol", "timeframe")}
        return safe, None

    @staticmethod
    def _valid_result(name: str, result: Any) -> tuple[bool, str | None]:
        if not isinstance(result, AgentResult) or result.agent != name:
            return False, "INVALID_AGENT_RESULT:" + name
        if not _text(result.agent_version):
            return False, "AGENT_VERSION_MISSING:" + name
        if not isinstance(result.state, str) or not _text(result.state):
            return False, "INVALID_AGENT_STATE:" + name
        if not isinstance(result.reason_codes, (tuple, list)) or len(result.reason_codes) > _MAX_REASON_CODES:
            return False, "INVALID_REASON_CODES:" + name
        if any(not isinstance(code, str) or not code or len(code) > _MAX_TEXT for code in result.reason_codes):
            return False, "INVALID_REASON_CODES:" + name
        if len(result.reason_codes) != len(set(result.reason_codes)):
            return False, "DUPLICATE_REASON_CODES:" + name
        if not isinstance(result.evidence_refs, (tuple, list)) or len(result.evidence_refs) > _MAX_EVIDENCE_REFS:
            return False, "INVALID_EVIDENCE_REFS:" + name
        if any(not isinstance(ref, str) or not ref or len(ref) > 512 for ref in result.evidence_refs):
            return False, "INVALID_EVIDENCE_REFS:" + name
        if not result.evidence_refs:
            return False, "MISSING_EVIDENCE_REFS:" + name
        if len(result.evidence_refs) != len(set(result.evidence_refs)):
            return False, "DUPLICATE_EVIDENCE_REFS:" + name
        return True, None

    @staticmethod
    def _trace_id(context: Mapping[str, Any]) -> str:
        material = {
            "version": MotherOrchestratorV1.VERSION,
            "scope": dict(context["scope"]),
            "observed_at": context["observed_at"],
            "snapshot_sha256": context["snapshot_sha256"],
            "evidence_sha256": context["evidence_sha256"],
            "request_id": context.get("request_id"),
        }
        raw = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return sha256(raw.encode()).hexdigest()

    def run(self, context: Mapping[str, Any]) -> OrchestrationResult:
        safe, context_error = self._validate_context(context)
        trace_id = self._trace_id(safe) if safe is not None else ""
        stages: list[AgentResult] = []
        reasons: list[str] = []
        consensus_result: dict[str, Any] | None = None

        def finish(status: str, decision: str, why: tuple[str, ...] | list[str]) -> OrchestrationResult:
            canonical_reasons = tuple(dict.fromkeys(str(x) for x in why if isinstance(x, str) and x))
            audit_rows = [{
                "agent": row.agent, "agent_version": row.agent_version, "state": row.state,
                "reason_codes": list(row.reason_codes),
                "evidence_refs": list(row.evidence_refs),
                "decision": _safe_decision(_decision_value(row.payload)) if row.agent == "decision" else None,
            } for row in stages]
            audit = {
                "version": self.VERSION, "trace_id": trace_id, "status": status,
                "decision": decision, "reason_codes": list(canonical_reasons),
                "stages": audit_rows, "consensus": deepcopy(consensus_result),
                "execution_authorized": False,
            }
            digest = sha256(json.dumps(audit, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            return OrchestrationResult(status, decision, tuple(stages), canonical_reasons, False,
                                       "hes.mother_orchestration.v1", trace_id, digest,
                                       deepcopy(consensus_result))

        if context_error:
            return finish("BLOCKED_CONTEXT", "NO_TRADE", (context_error,))
        missing = [name for name in self.REQUIRED if name not in self.agents]
        extra = [name for name in self.agents if name not in self.REQUIRED]
        if missing or extra:
            why = []
            if missing:
                why.append("MISSING_SPECIALISTS:" + ",".join(missing))
            if extra:
                why.append("UNREGISTERED_SPECIALISTS:" + ",".join(sorted(str(x) for x in extra)))
            return finish("BLOCKED_CONFIGURATION", "NO_TRADE", why)

        shared = safe
        gate_failures: list[str] = []
        risk_veto = False
        invalid_decision = False
        for name in self.REQUIRED:
            agent = self.agents[name]
            if getattr(agent, "name", None) != name or not callable(getattr(agent, "evaluate", None)):
                return finish("BLOCKED_CONFIGURATION", "NO_TRADE", ("INVALID_SPECIALIST_REGISTRATION:" + name,))
            try:
                stage_context = deepcopy(shared)
                result = agent.evaluate(stage_context)
            except Exception:
                return finish("BLOCKED_AGENT_ERROR", "NO_TRADE", ("AGENT_EXCEPTION:" + name,))
            valid, error = self._valid_result(name, result)
            if not valid:
                return finish("BLOCKED_INVALID_RESULT", "NO_TRADE", (error or "INVALID_AGENT_RESULT",))
            # Freeze caller-owned collections at the boundary; do not retain mutable aliases.
            try:
                result = AgentResult(result.agent, result.state, tuple(result.reason_codes),
                                     tuple(result.evidence_refs), deepcopy(result.payload), result.agent_version)
            except Exception:
                return finish("BLOCKED_INVALID_RESULT", "NO_TRADE", ("AGENT_PAYLOAD_NOT_COPYABLE:" + name,))
            stages.append(result)
            if result.state not in _ALLOWED[name]:
                # A failed gate is an observation, not a reason to suppress the
                # remaining independent specialists. In particular, confirmation
                # failure must not prevent Risk, Decision, and Evaluation from
                # running on the same immutable market snapshot. The final outcome
                # remains NO_TRADE and a risk rejection keeps veto precedence.
                gate_failures.append("AGENT_GATE_NOT_PASSED:" + name)
                gate_failures.extend(result.reason_codes)
                if name == "risk":
                    risk_veto = True
            if name == "decision":
                decision = _decision_value(result.payload)
                if _safe_decision(decision) == "INVALID":
                    invalid_decision = True
            shared[name] = result

        by_agent = {stage.agent: stage for stage in stages}
        consensus_result = resolve_mother_consensus_v1(context=safe, stage_results=by_agent)

        if invalid_decision:
            return finish("BLOCKED_INVALID_DECISION", "NO_TRADE", ("INVALID_DECISION",))
        if gate_failures:
            status = "BLOCKED_RISK_VETO" if risk_veto else "BLOCKED_GATE"
            return finish(status, "NO_TRADE", gate_failures)

        signal_payload = by_agent["signal"].payload
        confirmation_payload = by_agent["confirmation"].payload
        structure_payload = by_agent["market_structure"].payload
        signal_decision = signal_payload.get("decision") if isinstance(signal_payload, Mapping) else None
        confirmation_state = confirmation_payload.get("upstream_state") if isinstance(confirmation_payload, Mapping) else None
        regime = structure_payload.get("regime") if isinstance(structure_payload, Mapping) else None
        final_decision = _decision_value(by_agent["decision"].payload)
        if _safe_decision(final_decision) == "INVALID":
            return finish("BLOCKED_INVALID_DECISION", "NO_TRADE", ("INVALID_DECISION",))

        confirmed_direction = (
            confirmation_state.removeprefix("CONFIRMED_")
            if isinstance(confirmation_state, str) and confirmation_state in ("CONFIRMED_LONG", "CONFIRMED_SHORT")
            else None
        )
        conflict_class = consensus_result.get("conflict_class")
        consensus_decision = _safe_decision(consensus_result.get("decision"))
        if consensus_decision == "INVALID":
            return finish("BLOCKED_GATE", "NO_TRADE", ("CONSENSUS_DECISION_INVALID",))

        if conflict_class == "DIRECTION_CONFLICT":
            if signal_decision in ("LONG", "SHORT") and confirmed_direction in ("LONG", "SHORT") and signal_decision != confirmed_direction:
                why = ("SIGNAL_CONFIRMATION_DIRECTION_CONFLICT",)
            elif (
                (regime == "UPTREND" and signal_decision == "SHORT")
                or (regime == "DOWNTREND" and signal_decision == "LONG")
            ):
                why = ("MARKET_STRUCTURE_SIGNAL_DIRECTION_CONFLICT",)
            else:
                why = ("CONSENSUS_DIRECTION_CONFLICT",)
            return finish("BLOCKED_DIRECTION_CONFLICT", "NO_TRADE", why)

        if conflict_class not in ("CONSENSUS", "INSUFFICIENT_DIRECTIONAL_QUORUM", "NO_DIRECTION"):
            why = tuple(consensus_result.get("reason_codes") or ("CONSENSUS_NOT_VERIFIED",))
            return finish("BLOCKED_GATE", "NO_TRADE", why)

        if final_decision in ("LONG", "SHORT"):
            if consensus_decision != final_decision:
                return finish("BLOCKED_DIRECTION_CONFLICT", "NO_TRADE", ("FINAL_DECISION_DIRECTION_CONFLICT",))
            if regime == "RANGE":
                return finish("BLOCKED_DIRECTION_CONFLICT", "NO_TRADE", ("DIRECTIONAL_SIGNAL_IN_RANGE_REGIME",))
        return finish("OBSERVATION_ONLY", final_decision, ("EXECUTION_NOT_AUTHORIZED",))
