"""Live runtime adapters for the seven canonical Mother specialists.

Every request reads the shared validated Gate.io candle ledger and invokes the
existing deterministic HES evaluators. No saved Strategy V2 report is used as
the source of a specialist result. The module is read-only and never submits
orders or writes the decision journal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from core.orchestration.mother_v1 import AgentResult
from core.paper.strategy_v2_execution_gate import PaperExecutionGateV1, verify_gateio_1m_recovery_evidence
from forward.global_market_data_reader_v1 import (
    MarketDataRejected,
    build_market_data_batch_provenance,
    canonical_market_batch_sha256,
    load_market_input,
    read_closed_candles,
)
from forward.strategy_gate_pipeline_v1 import (
    PIPELINE_VERSION,
    evaluate_confirmation_evidence,
    evaluate_risk_evidence,
    inspect_structure,
)
from forward.strategy_policy_v2 import POLICY_VERSION, evaluate as evaluate_strategy
from forward.strategy_policy_gate_v1 import GATE_VERSION, enforce_final_gates
from forward.trade_journal_view_v1 import read_decision_journal
from scripts.analyze_gateio_snapshot_v1 import snapshot

SOURCE = "gateio_public_spot"
SYMBOL = "BTC_USDT"
TIMEFRAME = "15m"
DATA_QUALITY_VERSION = "hes-global-market-data-reader-runtime-v1"
EVALUATION_VERSION = "hes-forward-journal-observation-v1"
_REQUIRED = (
    "data_quality",
    "market_structure",
    "signal",
    "confirmation",
    "risk",
    "decision",
    "evaluation",
)


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")
    return sha256(raw).hexdigest()


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x for x in values if isinstance(x, str) and x))


def _batch_refs(provenance: Mapping[str, Any]) -> tuple[str, ...]:
    timeframes = provenance.get("timeframes", {})
    refs = []
    for timeframe in ("15m", "1h", "4h"):
        item = timeframes.get(timeframe, {}) if isinstance(timeframes, Mapping) else {}
        digest = item.get("input_batch_sha256") if isinstance(item, Mapping) else None
        if isinstance(digest, str) and len(digest) == 64:
            refs.append(f"market_batch:{timeframe}:sha256:{digest}")
    return tuple(refs)


class LiveMarketContextV1:
    """One-request, memoized view of the shared persisted Gate.io candle ledger."""

    def __init__(
        self,
        *,
        data_root: str | Path,
        observed_at: datetime | None = None,
        journal_path: str | Path | None = None,
    ) -> None:
        self.root = Path(data_root).expanduser().resolve()
        self.observed_at = observed_at or datetime.now(timezone.utc)
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        self.observed_at = self.observed_at.astimezone(timezone.utc)
        self.now_s = int(self.observed_at.timestamp())
        self.journal_path = Path(journal_path) if journal_path else self.root / "data/forward/trade_journal_v2.jsonl"
        self._loaded = False
        self.error: str | None = None
        self.market_input: dict[str, Any] | None = None
        self.provenance: dict[str, Any] | None = None
        self.precision_1m: dict[str, Any] = {"status": "BLOCKED", "reason": "NOT_CHECKED"}
        self.recovery_evidence: dict[str, Any] = {"status": "BLOCKED", "reason": "RECOVERY_EVIDENCE_NOT_CHECKED"}
        self.paper_gate: dict[str, Any] | None = None
        self.structure: dict[str, Any] | None = None
        self.frames: dict[str, Any] | None = None
        self.proposal: Any = None
        self.confirmation_bundle: dict[str, Any] | None = None
        self.risk_bundle: dict[str, Any] | None = None
        self.final_gate: dict[str, Any] | None = None
        self.journal: dict[str, Any] | None = None
        self.snapshot_sha256 = ""

    def load(self) -> dict[str, Any]:
        if self._loaded:
            if self.error:
                raise RuntimeError(self.error)
            assert self.market_input is not None
            return self.market_input
        self._loaded = True
        try:
            data = load_market_input(root=self.root, now=self.now_s, min_bars=200)
            if data.get("source") != SOURCE or data.get("symbol") != SYMBOL:
                raise MarketDataRejected("MARKET_IDENTITY_MISMATCH")
            provenance = build_market_data_batch_provenance(data)
            precision: dict[str, Any]
            try:
                rows_1m = read_closed_candles("1m", root=self.root, now=self.now_s, min_bars=200)
                precision = {
                    "status": "READY",
                    "bars": len(rows_1m),
                    "last_close_time": rows_1m[-1]["close_time"],
                    "age_seconds": max(0, self.now_s - int(rows_1m[-1]["close_time"])),
                    "input_batch_sha256": canonical_market_batch_sha256(rows_1m, limit=240),
                    "direction_authority": False,
                }
            except (MarketDataRejected, OSError, ValueError) as exc:
                precision = {
                    "status": "BLOCKED",
                    "reason": str(exc)[:160],
                    "bars": 0,
                    "direction_authority": False,
                }
            self.market_input = data
            self.provenance = provenance
            self.precision_1m = precision
            self.recovery_evidence = verify_gateio_1m_recovery_evidence(
                self.root / "data/forward/gateio_1m_recovery_24h_evidence.json",
                data_root=self.root,
                now=self.observed_at,
            )
            self.snapshot_sha256 = _canonical_hash({
                "market_data_provenance": provenance,
                "precision_1m": {
                    "status": precision.get("status"),
                    "input_batch_sha256": precision.get("input_batch_sha256"),
                    "reason": precision.get("reason"),
                },
            })
            return data
        except Exception as exc:
            self.error = f"{type(exc).__name__}:{str(exc)[:180]}"
            self.snapshot_sha256 = _canonical_hash({
                "source": SOURCE, "symbol": SYMBOL, "error": self.error,
            })
            raise

    def batch_refs(self) -> tuple[str, ...]:
        self.load()
        assert self.provenance is not None
        refs = list(_batch_refs(self.provenance))
        digest = self.precision_1m.get("input_batch_sha256")
        if isinstance(digest, str) and len(digest) == 64:
            refs.append(f"market_batch:1m:sha256:{digest}")
        elif self.precision_1m.get("reason"):
            refs.append("precision_entry_1m:blocked:" + str(self.precision_1m["reason"])[:100])
        return _unique(refs)

    def ensure_structure(self) -> dict[str, Any]:
        data = self.load()
        if self.structure is None:
            self.structure = inspect_structure(data["timeframes"]["15m"], self.observed_at)
        return self.structure

    def ensure_proposal(self):
        data = self.load()
        if self.proposal is None:
            self.frames = {
                timeframe: snapshot(timeframe, rows)
                for timeframe, rows in data["timeframes"].items()
            }
            self.proposal = evaluate_strategy(self.frames)
        return self.proposal

    def ensure_confirmation(self) -> dict[str, Any]:
        data = self.load()
        proposal = self.ensure_proposal()
        structure = self.ensure_structure()
        if self.confirmation_bundle is None:
            self.confirmation_bundle = evaluate_confirmation_evidence(
                proposal=proposal,
                structure=structure,
                source=data["source"],
                symbol=data["symbol"],
                observed_at=self.observed_at,
            )
        return self.confirmation_bundle

    def ensure_risk(self) -> dict[str, Any]:
        proposal = self.ensure_proposal()
        confirmation = self.ensure_confirmation()["confirmation"]
        if self.risk_bundle is None:
            self.risk_bundle = evaluate_risk_evidence(
                proposal=proposal,
                confirmation=confirmation,
                observed_at=self.observed_at,
            )
        return self.risk_bundle

    def ensure_final_gate(self) -> dict[str, Any]:
        if self.final_gate is None:
            proposal = self.ensure_proposal()
            structure = self.ensure_structure()
            confirmation = self.ensure_confirmation()["confirmation"]
            risk = self.ensure_risk()["risk"]
            gate_evidence = {
                "structure": structure,
                "confirmation": {
                    "state": confirmation.state,
                    "reason_codes": list(confirmation.reason_codes),
                },
                "risk": {
                    "state": risk.state,
                    "reason_codes": list(risk.reason_codes),
                },
            }
            final = enforce_final_gates(proposal, gate_evidence).as_dict()
            if proposal.decision in ("LONG", "SHORT") and self.precision_1m.get("status") != "READY":
                reasons = list(final.get("reasons", []))
                reasons.append("PRECISION_ENTRY_1M_FEED_NOT_READY")
                final.update({
                    "decision": "NO_TRADE",
                    "direction": "NONE",
                    "reasons": list(dict.fromkeys(reasons)),
                    "execution_enabled": False,
                    "orders_placed": False,
                })
            self.final_gate = final
        return self.final_gate

    @staticmethod
    def _read_activation_map(path: Path) -> dict[str, Any]:
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {"status": "INVALID"}
        return dict(value) if isinstance(value, Mapping) else {"status": "INVALID"}

    def paper_execution_gate(self) -> dict[str, Any]:
        if self.paper_gate is not None:
            return self.paper_gate
        try:
            data = self.load()
            structure = self.structure
            proposal = self.proposal
            confirmation = (
                self.confirmation_bundle.get("confirmation")
                if self.confirmation_bundle else None
            )
            risk = self.risk_bundle.get("risk") if self.risk_bundle else None
            timeframes = data["timeframes"]
            seconds = {"15m": 900, "1h": 3600, "4h": 14400}
            clock_safe = all(
                0 <= self.now_s - int(timeframes[tf][-1]["close_time"]) <= seconds[tf] * 2
                for tf in seconds
            )
            data_live = data.get("source") == SOURCE and data.get("symbol") == SYMBOL
            structure_safe = bool(
                structure and structure.get("status") == "OBSERVED"
                and structure.get("regime") != "UNKNOWN"
            )
            # load_market_input/read_closed_candles validate candle boundaries,
            # ordering, duplicates and gaps. No undocumented trade.sequence is used.
            sequence_safe = True
            health_safe = (
                self.precision_1m.get("status") == "READY" and clock_safe
            )
            policy = self._read_activation_map(self.root / "forward/strategy_policy_v2_activation.json")
            ruleset = self._read_activation_map(self.root / "forward/strategy_policy_v2_ruleset.json")
            result = PaperExecutionGateV1().evaluate(
                policy=policy,
                ruleset=ruleset,
                data_live=data_live,
                structure_safe=structure_safe,
                sequence_safe=sequence_safe,
                clock_safe=clock_safe,
                health_safe=health_safe,
                recovery_safe=self.recovery_evidence.get("status") == "VERIFIED",
                proposal_decision=proposal.decision if proposal else "NO_TRADE",
                confirmation_state=confirmation.state if confirmation else "NOT_EVALUATED",
                risk_state=risk.state if risk else "NOT_EVALUATED",
                precision_entry_ready=self.precision_1m.get("status") == "READY",
                execution_enabled=False,
                historical_inputs_allowed=False,
                future_outcomes_allowed=False,
            )
            self.paper_gate = result.as_dict()
        except Exception as exc:
            self.paper_gate = {
                "schema": "hes.paper_execution_gate.v1",
                "mode": "PAPER_SIMULATION_ONLY",
                "ready": False,
                "status": "BLOCKED",
                "paper_intent": None,
                "reason_codes": ["PAPER_GATE_EVALUATION_ERROR:" + type(exc).__name__],
                "execution_enabled": False,
                "orders_placed": False,
                "capital_mutated": False,
                "venue_adapter_called": False,
                "position_created": False,
            }
        return self.paper_gate

    def ensure_journal(self) -> dict[str, Any]:
        if self.journal is None:
            self.journal = read_decision_journal(
                self.journal_path,
                limit=100,
                now=self.observed_at,
                expected_source=SOURCE,
                expected_symbol=SYMBOL,
                expected_policy_version=POLICY_VERSION,
                require_execution_off=True,
            )
        return self.journal

    def summary(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source": SOURCE,
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "observed_at": self.observed_at.isoformat(),
            "snapshot_sha256": self.snapshot_sha256,
            "precision_entry": dict(self.precision_1m),
            "recovery_evidence": dict(self.recovery_evidence),
            "paper_execution_gate": self.paper_execution_gate(),
            "sequence_validation": {
                "status": "PASS" if self.market_input is not None and self.precision_1m.get("status") == "READY" else "BLOCKED",
                "basis": "CANDLE_OPEN_TIME_CONTINUITY",
                "trade_sequence_used": False,
                "trade_sequence_semantics": "UNKNOWN_NOT_USED",
                "scope": ["1m", "15m", "1h", "4h"],
                "note": "No trade ID or WebSocket sequence-like field is used as ordering, identity, or gap evidence.",
            },
            "market_data_provenance": self.provenance,
            "market_regime": "UNKNOWN",
            "strategy_proposal": {
                "decision": "NO_TRADE",
                "direction": "NONE",
                "reason_codes": ["LIVE_EVALUATION_NOT_REACHED"],
            },
        }
        if self.structure is not None:
            result["market_regime"] = self.structure.get("regime", "UNKNOWN")
        if self.proposal is not None:
            result["strategy_proposal"] = {
                "decision": self.proposal.decision,
                "direction": self.proposal.direction,
                "quality_score": self.proposal.quality_score,
                "reason_codes": list(self.proposal.reasons),
                "policy_version": self.proposal.policy_version,
            }
        if self.error:
            result["data_error"] = self.error
        return result


class DataQualitySpecialistV1:
    name = "data_quality"
    VERSION = DATA_QUALITY_VERSION

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        data = self.market.load()
        refs = self.market.batch_refs()
        if len(refs) < 3:
            raise ValueError("MARKET_DATA_PROVENANCE_INCOMPLETE")
        payload = {
            "source": data["source"],
            "symbol": data["symbol"],
            "timeframes": {
                timeframe: {
                    "bars": len(rows),
                    "last_closed_candle_time": rows[-1]["close_time"],
                }
                for timeframe, rows in data["timeframes"].items()
            },
            "precision_entry_1m": dict(self.market.precision_1m),
            "direction_authority_1m": False,
        }
        return AgentResult(self.name, "PASS", (), refs, payload, self.VERSION)


class MarketStructureSpecialistV1:
    name = "market_structure"
    VERSION = PIPELINE_VERSION + ":market-structure"

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        structure = self.market.ensure_structure()
        refs = _unique((*self.market.batch_refs(), "market_structure_sha256:" + _canonical_hash(structure)))
        passed = structure.get("status") == "OBSERVED" and structure.get("regime") != "UNKNOWN"
        reasons = () if passed else ("MARKET_STRUCTURE_NOT_OBSERVED_OR_REGIME_UNKNOWN",)
        return AgentResult(self.name, "PASS" if passed else "UNKNOWN", reasons, refs, structure, self.VERSION)


class SignalSpecialistV1:
    name = "signal"
    VERSION = POLICY_VERSION

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        proposal = self.market.ensure_proposal()
        payload = {
            "decision": proposal.decision,
            "direction": proposal.direction,
            "quality_score": proposal.quality_score,
            "entry": proposal.entry,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "rr": proposal.rr,
            "checks": dict(proposal.checks),
        }
        refs = _unique((*self.market.batch_refs(), "strategy_proposal_sha256:" + _canonical_hash(proposal.as_dict())))
        return AgentResult(self.name, "PASS", tuple(proposal.reasons), refs, payload, self.VERSION)


class ConfirmationSpecialistV1:
    name = "confirmation"
    VERSION = PIPELINE_VERSION + ":confirmation-policy"

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        bundle = self.market.ensure_confirmation()
        confirmation = bundle["confirmation"]
        upstream = str(confirmation.state or "UNCONFIRMED")
        news = context.get("news_context", {})
        news = news if isinstance(news, Mapping) else {}
        news_status = str(news.get("status") or "BLOCKED")
        news_veto_flags = news.get("veto_flags", [])
        news_veto_flags = tuple(sorted(set(
            flag for flag in news_veto_flags
            if isinstance(flag, str) and flag in {
                "HIGH_IMPACT_NEWS_REQUIRES_CONFIRMATION",
                "NEWS_TIMESTAMP_SUSPECT", "NEWS_TIMESTAMP_INVALID",
                "NEWS_TIMESTAMP_UNVERIFIED", "NEWS_SOURCE_UNVERIFIED",
            }
        ))) if isinstance(news_veto_flags, (list, tuple)) else ()
        state = "CONFIRMED" if upstream in ("CONFIRMED_LONG", "CONFIRMED_SHORT") and not news_veto_flags else "UNCONFIRMED"
        base_reasons = tuple(confirmation.reason_codes or (() if upstream in ("CONFIRMED_LONG", "CONFIRMED_SHORT") else ("CONFIRMATION_NOT_VALID",)))
        reasons = tuple(dict.fromkeys((*base_reasons, *news_veto_flags)))
        news_refs = tuple(
            value for value in (
                "news_snapshot_sha256:" + str(news.get("snapshot_sha256")) if news.get("snapshot_sha256") else None,
                "news_brief_sha256:" + str(news.get("brief_sha256")) if news.get("brief_sha256") else None,
            ) if value
        )
        refs = _unique((
            *self.market.batch_refs(),
            *news_refs,
            "confirmation_sha256:" + _canonical_hash({
                "state": confirmation.state,
                "passed_count": confirmation.passed_count,
                "required_count": confirmation.required_count,
                "reason_codes": list(confirmation.reason_codes),
                "checks": [
                    {"name": check.name, "state": check.state, "evidence_ref": check.evidence_ref,
                     "observed_at": check.observed_at.isoformat()}
                    for check in confirmation.checks
                ],
            }),
        ))
        payload = {
            "upstream_state": upstream,
            "direction": upstream.removeprefix("CONFIRMED_") if upstream.startswith("CONFIRMED_") and state == "CONFIRMED" else "NONE",
            "news_context_status": news_status,
            "news_veto_flags": list(news_veto_flags),
            "news_coverage_status": str(news.get("coverage_status") or "UNKNOWN"),
            "news_items": [
                {
                    "item_id": item.get("item_id"),
                    "interpretation": item.get("interpretation"),
                    "freshness": item.get("freshness"),
                }
                for item in news.get("findings", [])[:5]
                if isinstance(item, Mapping) and isinstance(item.get("interpretation"), Mapping)
            ] if isinstance(news.get("findings"), list) else [],
            "news_alone_can_authorize_trade": False,
        }
        return AgentResult(self.name, state, reasons, refs, payload, self.VERSION)


class RiskSpecialistV1:
    name = "risk"
    VERSION = PIPELINE_VERSION + ":risk-policy"

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        bundle = self.market.ensure_risk()
        risk = bundle["risk"]
        upstream = str(risk.state or "UNKNOWN")
        state = "APPROVED" if upstream == "RISK_APPROVED" else "REJECTED"
        reasons = tuple(risk.reason_codes or (() if state == "APPROVED" else ("RISK_GATE_NOT_APPROVED",)))
        checks = [
            {"name": check.name, "state": check.state, "evidence_ref": check.evidence_ref,
             "observed_at": check.observed_at.isoformat()}
            for check in risk.checks
        ]
        refs = _unique((*self.market.batch_refs(), "risk_sha256:" + _canonical_hash({
            "state": risk.state, "reason_codes": list(risk.reason_codes), "checks": checks,
        })))
        return AgentResult(
            self.name, state, reasons, refs,
            {"upstream_state": upstream, "checks": checks},
            self.VERSION,
        )


class DecisionSpecialistV1:
    name = "decision"
    VERSION = GATE_VERSION

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        decision = self.market.ensure_final_gate()
        decision["paper_execution_gate"] = self.market.paper_execution_gate()
        refs = _unique((*self.market.batch_refs(), "final_gate_sha256:" + _canonical_hash(decision)))
        return AgentResult(
            self.name, "DECIDED", tuple(decision.get("reasons", [])), refs,
            decision, self.VERSION,
        )


class EvaluationSpecialistV1:
    name = "evaluation"
    VERSION = EVALUATION_VERSION

    def __init__(self, market: LiveMarketContextV1):
        self.market = market

    def evaluate(self, context: Mapping[str, Any]) -> AgentResult:
        journal = self.market.ensure_journal()
        status = journal.get("status")
        if status not in ("VERIFIED", "EMPTY"):
            raise ValueError("DECISION_JOURNAL_NOT_VERIFIED")
        events = journal.get("events", [])
        if not isinstance(events, list):
            raise ValueError("DECISION_JOURNAL_EVENTS_INVALID")
        digest = _canonical_hash({
            "record_count": journal.get("count", 0),
            "decision_count": journal.get("decision_count", 0),
            "event_hashes": [event.get("event_sha256") for event in events if isinstance(event, Mapping)],
        })
        latest = events[0] if events else {}
        payload = {
            "journal_status": status,
            "decision_count": journal.get("decision_count", 0),
            "event_count": len(events),
            "latest_event_id": latest.get("event_id") if isinstance(latest, Mapping) else None,
            "latest_decision": latest.get("decision") if isinstance(latest, Mapping) else None,
            "journal_projection_sha256": digest,
            "outcomes_inferred": False,
            "evaluation_scope": "DECISION_OBSERVATION_ONLY",
        }
        refs = (f"decision_journal_projection_sha256:{digest}",)
        reasons = ("NO_DECISION_EVENTS_RECORDED",) if not events else ()
        return AgentResult(self.name, "OBSERVED", reasons, refs, payload, self.VERSION)


def live_specialists_v1(market: LiveMarketContextV1) -> dict[str, Any]:
    """Return the seven real runtime adapters in the canonical contract order."""
    agents = {
        "data_quality": DataQualitySpecialistV1(market),
        "market_structure": MarketStructureSpecialistV1(market),
        "signal": SignalSpecialistV1(market),
        "confirmation": ConfirmationSpecialistV1(market),
        "risk": RiskSpecialistV1(market),
        "decision": DecisionSpecialistV1(market),
        "evaluation": EvaluationSpecialistV1(market),
    }
    if tuple(agents) != _REQUIRED:
        raise RuntimeError("MOTHER_RUNTIME_SPECIALIST_REGISTRY_INVALID")
    return agents


def specialist_registry_v1() -> list[dict[str, str]]:
    """Stable registry metadata; distinct from which stages ran in this request."""
    return [
        {"name": "data_quality", "agent_version": DATA_QUALITY_VERSION},
        {"name": "market_structure", "agent_version": MarketStructureSpecialistV1.VERSION},
        {"name": "signal", "agent_version": POLICY_VERSION},
        {"name": "confirmation", "agent_version": ConfirmationSpecialistV1.VERSION},
        {"name": "risk", "agent_version": RiskSpecialistV1.VERSION},
        {"name": "decision", "agent_version": GATE_VERSION},
        {"name": "evaluation", "agent_version": EVALUATION_VERSION},
    ]
