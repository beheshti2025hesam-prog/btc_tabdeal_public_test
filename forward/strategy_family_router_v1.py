"""Fail-closed strategy-family routing contract for HES.

This module identifies the appropriate strategy family from the validated
15m regime. It does not generate candidates, approve a policy, bypass gates,
or enable execution. Existing trend-breakout behavior remains locked; RANGE
is explicitly routed to research-only until independently accepted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


RouterState = Literal["FAMILY_IDENTIFIED_NOT_AUTHORIZED", "NO_FAMILY"]
ActivationState = Literal["CANDIDATE_LOCKED_NOT_ACTIVE", "RESEARCH_ONLY_NOT_ACTIVE"]


@dataclass(frozen=True)
class StrategyFamilyProfile:
    family_id: str
    version: str
    regimes: tuple[str, ...]
    setup_timeframe: str
    precision_timeframe: str
    activation_state: ActivationState
    minimum_rr: float | None
    required_gates: tuple[str, ...]
    signal_generation_enabled: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False


@dataclass(frozen=True)
class StrategyFamilyRoute:
    router_version: str
    state: RouterState
    family_id: str | None
    family_version: str | None
    activation_state: ActivationState | None
    regime: str
    symbol: str
    timeframe: str
    reason_codes: tuple[str, ...]
    candidate_generation_authorized: bool = False
    execution_enabled: bool = False
    orders_placed: bool = False

    def as_dict(self) -> dict:
        result = asdict(self)
        result["reason_codes"] = list(self.reason_codes)
        return result


ROUTER_VERSION = "hes-strategy-family-router-v1.0.0"
CANONICAL_SOURCE = "gateio_public_spot"
CANONICAL_SYMBOL = "BTC_USDT"
SETUP_TIMEFRAME = "15m"
PRECISION_TIMEFRAME = "1m"

TREND_BREAKOUT_V2 = StrategyFamilyProfile(
    family_id="trend_breakout",
    version="hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
    regimes=("UPTREND", "DOWNTREND"),
    setup_timeframe=SETUP_TIMEFRAME,
    precision_timeframe=PRECISION_TIMEFRAME,
    activation_state="CANDIDATE_LOCKED_NOT_ACTIVE",
    minimum_rr=3.0,
    required_gates=(
        "HTF_1H_4H_ALIGNMENT",
        "CLOSED_15M_20_BAR_BREAKOUT",
        "EMA50_VWAP20_LOCATION",
        "RSI_MFI_FLOW_CONFIRMATION",
        "STRUCTURE_CONFIRMATION",
        "INDEPENDENT_CONFIRMATION_GATE",
        "INDEPENDENT_RISK_GATE",
        "FINAL_POLICY_APPROVAL",
    ),
)

RANGE_MEAN_REVERSION_RESEARCH_V1 = StrategyFamilyProfile(
    family_id="range_mean_reversion",
    version="hes-range-mean-reversion-research-v1.1",
    regimes=("RANGE",),
    setup_timeframe=SETUP_TIMEFRAME,
    precision_timeframe=PRECISION_TIMEFRAME,
    activation_state="RESEARCH_ONLY_NOT_ACTIVE",
    # The research prototype's 1.2R net handoff floor is not an approved
    # family threshold; keep it unset until a preregistered profile is accepted.
    minimum_rr=None,
    required_gates=(
        "RANGE_PERSISTENCE_AND_BOUNDARY_LOCATION",
        "REVERSAL_STRUCTURE_CONFIRMATION",
        "COST_ADJUSTED_ENTRY_GEOMETRY",
        "INDEPENDENT_CONFIRMATION_GATE",
        "INDEPENDENT_RISK_GATE",
        "INDEPENDENT_OUT_OF_SAMPLE_ACCEPTANCE",
        "EXPLICIT_POLICY_APPROVAL",
    ),
)

_PROFILES = (TREND_BREAKOUT_V2, RANGE_MEAN_REVERSION_RESEARCH_V1)


def route_strategy_family(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    regime: str,
) -> StrategyFamilyRoute:
    """Identify a family without authorizing candidate generation or trading.

    Only the canonical Gate.io BTC_USDT 15m setup context is routed in v1.
    The 1m timeframe remains a downstream precision-entry layer.
    """
    normalized_regime = regime if isinstance(regime, str) else "UNKNOWN"
    if source != CANONICAL_SOURCE:
        return _no_family(symbol, timeframe, normalized_regime, "NON_CANONICAL_MARKET_DATA_SOURCE")
    if symbol != CANONICAL_SYMBOL:
        return _no_family(symbol, timeframe, normalized_regime, "SYMBOL_OUT_OF_V1_SCOPE")
    if timeframe != SETUP_TIMEFRAME:
        reason = "PRECISION_TIMEFRAME_CANNOT_GENERATE_SETUP" if timeframe == PRECISION_TIMEFRAME else "TIMEFRAME_OUT_OF_V1_SCOPE"
        return _no_family(symbol, timeframe, normalized_regime, reason)

    for profile in _PROFILES:
        if normalized_regime in profile.regimes:
            return StrategyFamilyRoute(
                router_version=ROUTER_VERSION,
                state="FAMILY_IDENTIFIED_NOT_AUTHORIZED",
                family_id=profile.family_id,
                family_version=profile.version,
                activation_state=profile.activation_state,
                regime=normalized_regime,
                symbol=symbol,
                timeframe=timeframe,
                reason_codes=("FAMILY_ROUTED_BUT_NOT_AUTHORIZED", profile.activation_state),
            )
    return _no_family(symbol, timeframe, normalized_regime, "REGIME_HAS_NO_APPROVED_FAMILY")


def _no_family(symbol: str, timeframe: str, regime: str, reason: str) -> StrategyFamilyRoute:
    return StrategyFamilyRoute(
        router_version=ROUTER_VERSION,
        state="NO_FAMILY",
        family_id=None,
        family_version=None,
        activation_state=None,
        regime=regime,
        symbol=symbol,
        timeframe=timeframe,
        reason_codes=(reason,),
    )
