"""Mother Agent - Capital & Risk Engine v1.0

Pure calculation and hard-veto layer. No exchange or order execution.
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class RiskConfig:
    account_equity: float
    risk_per_trade: float = 0.01
    max_leverage: float = 1.0
    max_position_notional: float | None = None
    min_reward_risk: float = 3.0


@dataclass(frozen=True)
class RiskSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class RiskAssessment:
    allowed: bool
    position_size: float
    notional: float
    risk_amount: float
    reasons: tuple[str, ...]


class CapitalRiskEngine:
    """Calculate position sizing and reject unsafe trade geometry."""

    def __init__(self, config: RiskConfig):
        if config.account_equity <= 0:
            raise ValueError("account_equity must be positive")
        if not 0 < config.risk_per_trade <= 1:
            raise ValueError("risk_per_trade must be in (0, 1]")
        if config.max_leverage <= 0:
            raise ValueError("max_leverage must be positive")
        if config.min_reward_risk <= 0:
            raise ValueError("min_reward_risk must be positive")
        self.config = config

    def assess(
        self,
        *,
        entry_price: float,
        stop_price: float,
        target_price: float,
        side: RiskSide = RiskSide.LONG,
    ) -> RiskAssessment:
        if entry_price <= 0 or stop_price <= 0 or target_price <= 0:
            return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_prices",))

        side_value = getattr(side, "value", side)
        if side_value not in (RiskSide.LONG.value, RiskSide.SHORT.value):
            return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_side",))

        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return RiskAssessment(False, 0.0, 0.0, 0.0, ("zero_stop_distance",))

        if side_value == RiskSide.LONG.value:
            if stop_price > entry_price:
                return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_long_stop",))
            if target_price <= entry_price:
                return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_long_target",))
        else:
            if stop_price < entry_price:
                return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_short_stop",))
            if target_price >= entry_price:
                return RiskAssessment(False, 0.0, 0.0, 0.0, ("invalid_short_target",))

        reward_distance = abs(target_price - entry_price)
        rr = reward_distance / stop_distance
        reasons: list[str] = []
        if rr < self.config.min_reward_risk:
            reasons.append("reward_risk_below_minimum")

        risk_amount = self.config.account_equity * self.config.risk_per_trade
        position_size = risk_amount / stop_distance
        notional = position_size * entry_price

        leverage_cap = self.config.account_equity * self.config.max_leverage
        if notional > leverage_cap:
            reasons.append("leverage_limit")
            position_size = leverage_cap / entry_price
            notional = leverage_cap

        if (
            self.config.max_position_notional is not None
            and notional > self.config.max_position_notional
        ):
            reasons.append("position_notional_limit")
            notional = self.config.max_position_notional
            position_size = notional / entry_price

        return RiskAssessment(
            allowed=not reasons,
            position_size=position_size if not reasons else 0.0,
            notional=notional if not reasons else 0.0,
            risk_amount=risk_amount,
            reasons=tuple(reasons),
        )
