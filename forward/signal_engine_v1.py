"""Forward Signal Engine v1 contract/skeleton.

This module intentionally contains NO trading thresholds or strategy rules.

Pipeline:
    standardized market input
        -> structure state
        -> opportunity candidate
        -> confirmation state
        -> risk state
        -> decision: LONG | SHORT | NO_TRADE

Design invariants:
- forward-only observations
- no future-outcome leakage
- NO_TRADE is a first-class decision
- LONG/SHORT symmetry
- quality_score is contemporaneous only
- risk may veto a candidate
- strategy parameters belong to a future, versioned policy layer
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Literal


Decision = Literal["LONG", "SHORT", "NO_TRADE"]


@dataclass(frozen=True)
class MarketInput:
    """Normalized, contemporaneous market state.

    The engine does not define how these values are calculated.
    Upstream adapters/features must provide them.
    """

    observed_at: datetime
    symbol: str
    timeframe: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class StructureState:
    """Market-structure result supplied by an upstream feature layer."""

    state: str
    values: Mapping[str, Any]


@dataclass(frozen=True)
class OpportunityCandidate:
    """A candidate opportunity before confirmation and risk gating."""

    direction: Literal["LONG", "SHORT"]
    reason_codes: tuple[str, ...] = ()
    values: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ConfirmationState:
    """Multi-layer confirmation result.

    This contract deliberately does not define confirmation thresholds.
    """

    state: str
    reason_codes: tuple[str, ...] = ()
    quality_score: Optional[float] = None
    values: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class RiskState:
    """Risk-gate result supplied by the risk layer."""

    state: str
    reason_codes: tuple[str, ...] = ()
    values: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class DecisionResult:
    """Immutable decision emitted by the forward engine."""

    decision: Decision
    observed_at: datetime
    symbol: str
    timeframe: str
    market_regime: str
    direction: str
    signal_state: str
    confirmation_state: str
    risk_state: str
    entry: Any = None
    stop_loss: Any = None
    take_profit: Any = None
    rr: Any = None
    quality_score: Optional[float] = None
    no_trade_reason: Optional[str] = None

    def as_journal_record(self, event_id: str, evidence_source: str) -> dict[str, Any]:
        """Return the v1 journal-shaped record.

        Outcome fields are intentionally empty at decision time.
        They must never influence this decision after the fact.
        """

        if self.decision == "NO_TRADE" and not self.no_trade_reason:
            raise ValueError("NO_TRADE requires no_trade_reason.")

        return {
            "event_id": event_id,
            "observed_at": self.observed_at.isoformat(),
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "market_regime": self.market_regime,
            "direction": self.direction,
            "signal_state": self.signal_state,
            "confirmation_state": self.confirmation_state,
            "risk_state": self.risk_state,
            "decision": self.decision,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "rr": self.rr,
            "quality_score": self.quality_score,
            "no_trade_reason": self.no_trade_reason,
            "outcome": None,
            "closed_at": None,
            "evidence_source": evidence_source,
        }


class ForwardSignalEngineV1:
    """Contract-only orchestration shell.

    Strategy logic is intentionally not implemented here. This prevents
    accidental threshold invention and keeps policy separate from the
    immutable forward data/decision contract.
    """

    VERSION = "forward-signal-engine-v1"

    def evaluate(
        self,
        market: MarketInput,
        structure: StructureState,
        candidate: Optional[OpportunityCandidate],
        confirmation: ConfirmationState,
        risk: RiskState,
    ) -> DecisionResult:
        """Emit a decision from already-computed layer states.

        Until a versioned policy is explicitly introduced, this shell
        fails closed with NO_TRADE rather than inventing trading rules.
        """

        if candidate is None:
            return DecisionResult(
                decision="NO_TRADE",
                observed_at=market.observed_at,
                symbol=market.symbol,
                timeframe=market.timeframe,
                market_regime=structure.state,
                direction="NONE",
                signal_state="NO_CANDIDATE",
                confirmation_state=confirmation.state,
                risk_state=risk.state,
                quality_score=confirmation.quality_score,
                no_trade_reason="NO_CANDIDATE",
            )

        return DecisionResult(
            decision="NO_TRADE",
            observed_at=market.observed_at,
            symbol=market.symbol,
            timeframe=market.timeframe,
            market_regime=structure.state,
            direction=candidate.direction,
            signal_state="CANDIDATE_PRESENT",
            confirmation_state=confirmation.state,
            risk_state=risk.state,
            quality_score=confirmation.quality_score,
            no_trade_reason="POLICY_NOT_CONFIGURED",
        )
