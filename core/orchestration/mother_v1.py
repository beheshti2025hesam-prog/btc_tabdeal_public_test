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

    def as_dict(self) -> dict[str, Any]:
        rows = []
        for stage in self.stages:
            payload = stage.payload if isinstance(stage.payload, Mapping) else {}
            row: dict[str, Any] = {
                "agent": stage.agent,
                "state": stage.state,
                "reason_codes": list(stage.reason_codes),
                "evidence_refs": list(stage.evidence_refs),
            }
            if stage.agent == "decision":
                row["decision"] = payload.get("decision")
            rows.append(row)
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "execution_authorized": False,
            "trace_id": self.trace_id,
            "audit_sha256": self.audit_sha256,
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


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256.fullmatch(value))


def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= _MAX_TEXT


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
        safe["observed_at"] = observed_at.isoformat()
        safe["scope"] = {key: scope[key] for key in ("venue", "product", "symbol", "timeframe")}
        return safe, None

    @staticmethod
    def _valid_result(name: str, result: Any) -> tuple[bool, str | None]:
        if not isinstance(result, AgentResult) or result.agent != name:
            return False, "INVALID_AGENT_RESULT:" + name
        if not isinstance(result.state, str) or not _text(result.state):
            return False, "INVALID_AGENT_STATE:" + name
        if not isinstance(result.reason_codes, (tuple, list)) or len(result.reason_codes) > _MAX_REASON_CODES:
            return False, "INVALID_REASON_CODES:" + name
        if any(not isinstance(code, str) or not code or len(code) > _MAX_TEXT for code in result.reason_codes):
            return False, "INVALID_REASON_CODES:" + name
        if not isinstance(result.evidence_refs, (tuple, list)) or len(result.evidence_refs) > _MAX_EVIDENCE_REFS:
            return False, "INVALID_EVIDENCE_REFS:" + name
        if any(not isinstance(ref, str) or not ref or len(ref) > 512 for ref in result.evidence_refs):
            return False, "INVALID_EVIDENCE_REFS:" + name
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

        def finish(status: str, decision: str, why: tuple[str, ...] | list[str]) -> OrchestrationResult:
            canonical_reasons = tuple(dict.fromkeys(str(x) for x in why if isinstance(x, str) and x))
            audit_rows = [{
                "agent": row.agent, "state": row.state,
                "reason_codes": list(row.reason_codes),
                "evidence_refs": list(row.evidence_refs),
                "decision": _decision_value(row.payload) if row.agent == "decision" else None,
            } for row in stages]
            audit = {
                "version": self.VERSION, "trace_id": trace_id, "status": status,
                "decision": decision, "reason_codes": list(canonical_reasons),
                "stages": audit_rows, "execution_authorized": False,
            }
            digest = sha256(json.dumps(audit, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
            return OrchestrationResult(status, decision, tuple(stages), canonical_reasons, False,
                                       "hes.mother_orchestration.v1", trace_id, digest)

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
            result = AgentResult(result.agent, result.state, tuple(result.reason_codes),
                                 tuple(result.evidence_refs), deepcopy(result.payload))
            stages.append(result)
            if result.state not in _ALLOWED[name]:
                reasons = result.reason_codes or ("AGENT_GATE_NOT_PASSED:" + name,)
                status = "BLOCKED_RISK_VETO" if name == "risk" else "BLOCKED_GATE"
                return finish(status, "NO_TRADE", reasons)
            if name == "decision":
                decision = _decision_value(result.payload)
                if decision not in {"LONG", "SHORT", "NO_TRADE"}:
                    return finish("BLOCKED_INVALID_DECISION", "NO_TRADE", ("INVALID_DECISION",))
            shared[name] = result

        final_decision = _decision_value(stages[-2].payload)
        if final_decision not in {"LONG", "SHORT", "NO_TRADE"}:
            return finish("BLOCKED_INVALID_DECISION", "NO_TRADE", ("INVALID_DECISION",))
        return finish("OBSERVATION_ONLY", final_decision, ("EXECUTION_NOT_AUTHORIZED",))
