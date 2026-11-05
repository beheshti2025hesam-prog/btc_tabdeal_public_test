"""Auditable, fail-closed arbitration over existing specialist-agent outputs.

This is a thin orchestration contract, not another indicator/strategy engine.
No order execution occurs here. Mandatory vetoes always beat majority opinion.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from itertools import islice
from typing import Iterable


VALID_STATES = {"PASS", "FAIL", "UNKNOWN"}
VALID_DIRECTIONS = {"LONG", "SHORT", "NEUTRAL", "UNKNOWN"}
MANDATORY_VETO_AGENTS = frozenset({"data_quality", "strategy", "confirmation", "risk"})
# Callers may add requirements, but cannot weaken the minimum safety quorum.
CORE_REQUIRED_AGENTS = MANDATORY_VETO_AGENTS | frozenset({"market_structure"})
# A directional result requires two distinct policy/confirmation authorities.
DIRECTIONAL_REQUIRED_AGENTS = frozenset({"strategy", "confirmation"})
MAX_ASSESSMENTS = 32
MAX_REQUIRED_AGENTS = 32
MAX_REASON_CODES = 64
MAX_SCOPE_TEXT = 128
MAX_REASON_CODE = 128


@dataclass(frozen=True)
class AgentAssessmentV1:
    agent_id: str
    agent_version: str
    state: str
    direction: str
    venue: str
    product: str
    symbol: str
    timeframe: str
    as_of: datetime
    snapshot_sha256: str
    evidence_sha256: str
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArbitrationResultV1:
    decision: str
    direction: str
    conflict_class: str
    reason_codes: tuple[str, ...]
    assessments: tuple[dict, ...]
    audit_sha256: str

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "direction": self.direction,
            "conflict_class": self.conflict_class,
            "reason_codes": list(self.reason_codes),
            "assessments": [dict(item) for item in self.assessments],
            "audit_sha256": self.audit_sha256,
        }


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("assessment timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


class AgentDisagreementResolverV1:
    """Resolve one same-snapshot set of specialist assessments deterministically."""

    VERSION = "hes-agent-disagreement-resolver-v1"

    def resolve(
        self,
        *,
        assessments: Iterable[AgentAssessmentV1],
        observed_at: datetime,
        required_agents: Iterable[str] = ("data_quality", "market_structure", "strategy", "confirmation", "risk"),
    ) -> ArbitrationResultV1:
        decision, direction = "NO_TRADE", "UNKNOWN"

        def finish(classification: str, reason_codes: Iterable[str], rows: list[dict]) -> ArbitrationResultV1:
            canonical_reasons = tuple(sorted(set(reason_codes)))
            payload = {
                "resolver_version": self.VERSION,
                "decision": decision,
                "direction": direction,
                "conflict_class": classification,
                "reason_codes": list(canonical_reasons),
                "assessments": rows,
            }
            digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            return ArbitrationResultV1(decision, direction, classification, canonical_reasons, tuple(rows), digest)

        try:
            now = _utc(observed_at)
        except (TypeError, ValueError):
            return finish("INVALID_TIMESTAMP", ("OBSERVATION_TIMESTAMP_INVALID",), [])

        if isinstance(assessments, (str, bytes)):
            return finish("INVALID_ASSESSMENT_SET", ("ASSESSMENTS_NOT_AN_ITERABLE_OF_REPORTS",), [])
        try:
            items = tuple(islice(iter(assessments), MAX_ASSESSMENTS + 1))
        except Exception:
            return finish("INVALID_ASSESSMENT_SET", ("ASSESSMENT_ITERATION_FAILED",), [])
        if len(items) > MAX_ASSESSMENTS:
            return finish("ASSESSMENT_LIMIT_EXCEEDED", ("ASSESSMENT_COUNT_LIMIT_EXCEEDED",), [])
        if not items:
            return finish("MISSING_ASSESSMENTS", ("NO_ASSESSMENTS",), [])

        if isinstance(required_agents, (str, bytes)):
            return finish("INVALID_REQUIRED_AGENT_SET", ("REQUIRED_AGENTS_MUST_BE_A_COLLECTION",), [])
        try:
            requested_required = tuple(islice(iter(required_agents), MAX_REQUIRED_AGENTS + 1))
        except Exception:
            return finish("INVALID_REQUIRED_AGENT_SET", ("REQUIRED_AGENT_ITERATION_FAILED",), [])
        if len(requested_required) > MAX_REQUIRED_AGENTS:
            return finish("INVALID_REQUIRED_AGENT_SET", ("REQUIRED_AGENT_COUNT_LIMIT_EXCEEDED",), [])
        if any(
            not isinstance(name, str) or not name or name != name.strip() or len(name) > MAX_SCOPE_TEXT
            for name in requested_required
        ):
            return finish("INVALID_REQUIRED_AGENT_SET", ("REQUIRED_AGENT_NAME_INVALID",), [])
        required = tuple(sorted(set(requested_required) | CORE_REQUIRED_AGENTS))

        rows: list[dict] = []
        seen: set[str] = set()
        for a in items:
            if not isinstance(a, AgentAssessmentV1):
                return finish("INVALID_ASSESSMENT", ("ASSESSMENT_TYPE_INVALID",), rows)
            try:
                stamp = _utc(a.as_of)
            except (TypeError, ValueError):
                return finish("INVALID_TIMESTAMP", ("ASSESSMENT_TIMESTAMP_INVALID",), rows)

            if (
                not isinstance(a.agent_id, str) or not a.agent_id or a.agent_id != a.agent_id.strip()
                or len(a.agent_id) > MAX_SCOPE_TEXT
                or not isinstance(a.agent_version, str) or not a.agent_version
                or a.agent_version != a.agent_version.strip() or len(a.agent_version) > MAX_SCOPE_TEXT
                or not isinstance(a.state, str) or a.state not in VALID_STATES
                or not isinstance(a.direction, str) or a.direction not in VALID_DIRECTIONS
            ):
                return finish("INVALID_ASSESSMENT", ("ASSESSMENT_FIELDS_INVALID",), rows)
            if a.agent_id in seen:
                return finish("DUPLICATE_REPORT", ("DUPLICATE_AGENT_REPORT:" + a.agent_id,), rows)
            seen.add(a.agent_id)
            if stamp > now:
                return finish("FUTURE_EVIDENCE", ("FUTURE_EVIDENCE_REJECTED:" + a.agent_id,), rows)
            scope_values = (a.venue, a.product, a.symbol, a.timeframe)
            if any(
                not isinstance(value, str) or not value or value != value.strip() or len(value) > MAX_SCOPE_TEXT
                for value in scope_values
            ):
                return finish("INVALID_SCOPE", ("ASSESSMENT_SCOPE_MISSING:" + a.agent_id,), rows)
            if not _digest(a.snapshot_sha256) or not _digest(a.evidence_sha256):
                return finish("INVALID_PROVENANCE", ("EVIDENCE_HASH_INVALID:" + a.agent_id,), rows)
            if (
                not isinstance(a.reason_codes, (tuple, list))
                or len(a.reason_codes) > MAX_REASON_CODES
                or any(
                not isinstance(code, str) or not code or code != code.strip() or len(code) > MAX_REASON_CODE
                for code in a.reason_codes
                )
            ):
                return finish("INVALID_REASON_CODES", ("ASSESSMENT_REASON_CODES_INVALID:" + a.agent_id,), rows)
            if len(a.reason_codes) != len(set(a.reason_codes)):
                return finish("INVALID_REASON_CODES", ("ASSESSMENT_REASON_CODES_DUPLICATED:" + a.agent_id,), rows)

            rows.append({
                "agent_id": a.agent_id, "agent_version": a.agent_version,
                "state": a.state, "direction": a.direction,
                "scope": list(scope_values),
                "as_of": stamp.isoformat(), "snapshot_sha256": a.snapshot_sha256,
                "evidence_sha256": a.evidence_sha256,
                "reason_codes": sorted(a.reason_codes),
            })

        missing = sorted(set(required) - seen)
        if missing:
            return finish("MISSING_REQUIRED_AGENT", tuple("MISSING_REQUIRED_AGENT:" + name for name in missing), rows)
        scopes = {tuple(r["scope"]) for r in rows}
        snapshots = {r["snapshot_sha256"] for r in rows}
        stamps = {r["as_of"] for r in rows}
        if len(scopes) != 1:
            return finish("SCOPE_MISMATCH", ("AGENT_SCOPE_MISMATCH",), rows)
        if len(snapshots) != 1:
            return finish("SNAPSHOT_MISMATCH", ("COMMON_SNAPSHOT_HASH_MISMATCH",), rows)
        if len(stamps) != 1 or stamps != {now.isoformat()}:
            return finish("AS_OF_MISMATCH", ("ASSESSMENTS_NOT_BOUND_TO_OBSERVED_AT",), rows)

        unknown = sorted(r["agent_id"] for r in rows if r["state"] == "UNKNOWN" or r["direction"] == "UNKNOWN")
        if unknown:
            return finish("UNKNOWN_EVIDENCE", tuple("UNKNOWN_EVIDENCE:" + name for name in unknown), rows)
        failed = sorted(r["agent_id"] for r in rows if r["state"] == "FAIL")
        if failed:
            return finish("MANDATORY_VETO", tuple("AGENT_VETO:" + name for name in failed), rows)
        mandatory_not_pass = sorted(
            r["agent_id"] for r in rows
            if r["agent_id"] in CORE_REQUIRED_AGENTS and r["state"] != "PASS"
        )
        if mandatory_not_pass:
            return finish("MANDATORY_VETO", tuple("MANDATORY_GATE_NOT_PASSED:" + name for name in mandatory_not_pass), rows)

        directional_missing = sorted(
            name for name in DIRECTIONAL_REQUIRED_AGENTS
            if next((r["direction"] for r in rows if r["agent_id"] == name), "UNKNOWN") not in ("LONG", "SHORT")
        )
        if directional_missing:
            return finish(
                "INSUFFICIENT_DIRECTIONAL_QUORUM",
                tuple("DIRECTIONAL_QUORUM_NOT_MET:" + name for name in directional_missing),
                rows,
            )

        opinions = {r["direction"] for r in rows if r["direction"] in ("LONG", "SHORT")}
        if len(opinions) > 1:
            return finish("DIRECTION_CONFLICT", ("CONTRADICTORY_LONG_SHORT_OPINIONS",), rows)
        if not opinions:
            return finish("NO_DIRECTION", ("NO_DIRECTIONAL_CONSENSUS",), rows)
        selected = next(iter(opinions))
        if any(r["direction"] not in (selected, "NEUTRAL") for r in rows):
            return finish("DIRECTION_CONFLICT", ("INCOMPATIBLE_AGENT_DIRECTIONS",), rows)
        decision, direction = selected, selected
        return finish("CONSENSUS", ("ALL_REQUIRED_GATES_PASSED",), rows)
