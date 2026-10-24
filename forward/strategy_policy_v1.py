"""Versioned forward-only strategy evidence quorum.

This policy validates externally computed evidence; it does not calculate
indicators, infer market structure, tune thresholds, or execute orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Literal, Sequence

EvidenceState = Literal["PASS", "FAIL", "UNKNOWN"]

REQUIRED_CHECKS = (
    "htf_trend_alignment",
    "pullback_location",
    "reversal_break_confirmation",
    "mfi_confirmation",
    "adx_directional_strength",
    "risk_geometry_3_to_1",
)
MINIMUM_PASSES = 5
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StrategyEvidenceCheckV1:
    name: str
    state: EvidenceState
    evidence_ref: str
    evidence_sha256: str
    provider: str
    provider_version: str
    observed_at: datetime


@dataclass(frozen=True)
class StrategyQualityResultV1:
    policy_version: str
    state: EvidenceState
    venue: str
    product: str
    symbol: str
    timeframe: str
    direction: str
    passed_count: int
    required_count: int
    checks: tuple[StrategyEvidenceCheckV1, ...]
    reason_codes: tuple[str, ...]
    evidence_sha256: str | None


class StrategyPolicyV1:
    """Require 5/6 independently evidenced checks and always require valid risk geometry.

    The sixth check is the mandatory 3:1 risk-geometry gate. Therefore a
    passing result requires at least four of the five market confirmations
    plus risk geometry. All six checks must be present and measurable; UNKNOWN
    is not silently counted as a failed-but-usable confirmation.
    """

    VERSION = "hes-strategy-policy-v1"
    MINIMUM_PASSES = MINIMUM_PASSES
    REQUIRED = REQUIRED_CHECKS

    def evaluate(
        self,
        *,
        observed_at: datetime,
        venue: str,
        product: str,
        symbol: str,
        timeframe: str,
        direction: str,
        checks: Sequence[StrategyEvidenceCheckV1] = (),
    ) -> StrategyQualityResultV1:
        checks = tuple(checks)
        reasons: list[str] = []
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
            return StrategyQualityResultV1(self.VERSION, "UNKNOWN", venue, product, symbol, timeframe,
                direction, 0, self.MINIMUM_PASSES, checks, ("OBSERVED_AT_INVALID",), None)

        for field_name, value in (
            ("VENUE", venue), ("PRODUCT", product), ("SYMBOL", symbol),
            ("TIMEFRAME", timeframe), ("DIRECTION", direction),
        ):
            if not isinstance(value, str) or not value.strip():
                reasons.append(field_name + "_MISSING")
        if direction not in ("BULLISH", "BEARISH"):
            reasons.append("DIRECTION_NOT_ESTABLISHED")

        names = [getattr(c, "name", None) for c in checks]
        valid_names = [n for n in names if isinstance(n, str) and n.strip()]
        if len(valid_names) != len(set(valid_names)):
            reasons.append("DUPLICATE_STRATEGY_CHECK")
        if any(not isinstance(n, str) or not n.strip() for n in names):
            reasons.append("STRATEGY_CHECK_NAME_MISSING")

        by_name = {c.name: c for c in checks if isinstance(getattr(c, "name", None), str)}
        missing = tuple(name for name in self.REQUIRED if name not in by_name)
        if missing:
            reasons.extend("MISSING_" + name.upper() for name in missing)

        for check in checks:
            if not isinstance(check, StrategyEvidenceCheckV1):
                reasons.append("STRATEGY_CHECK_TYPE_INVALID")
                continue
            if check.state not in ("PASS", "FAIL", "UNKNOWN"):
                reasons.append("STRATEGY_CHECK_STATE_INVALID")
            if not isinstance(check.evidence_ref, str) or not check.evidence_ref.strip():
                reasons.append("STRATEGY_EVIDENCE_REFERENCE_MISSING")
            if not isinstance(check.evidence_sha256, str) or not _HASH_RE.fullmatch(check.evidence_sha256):
                reasons.append("STRATEGY_EVIDENCE_HASH_INVALID")
            if not isinstance(check.provider, str) or not check.provider.strip():
                reasons.append("STRATEGY_PROVIDER_MISSING")
            if not isinstance(check.provider_version, str) or not check.provider_version.strip():
                reasons.append("STRATEGY_PROVIDER_VERSION_MISSING")
            stamp = check.observed_at
            if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
                reasons.append("STRATEGY_EVIDENCE_TIMESTAMP_INVALID")
            elif stamp > observed_at:
                reasons.append("FUTURE_STRATEGY_EVIDENCE_REJECTED")

        # No score is emitted for incomplete, malformed, or temporally invalid evidence.
        if reasons:
            return StrategyQualityResultV1(self.VERSION, "UNKNOWN", venue, product, symbol, timeframe,
                direction, sum(getattr(c, "state", None) == "PASS" for c in checks), self.MINIMUM_PASSES,
                checks, tuple(dict.fromkeys(reasons)), None)

        if any(by_name[name].state == "UNKNOWN" for name in self.REQUIRED):
            return StrategyQualityResultV1(self.VERSION, "UNKNOWN", venue, product, symbol, timeframe,
                direction, sum(by_name[name].state == "PASS" for name in self.REQUIRED),
                self.MINIMUM_PASSES, checks, ("STRATEGY_EVIDENCE_UNKNOWN",), None)

        passed = sum(by_name[name].state == "PASS" for name in self.REQUIRED)
        if by_name["risk_geometry_3_to_1"].state != "PASS":
            reasons.append("MANDATORY_RISK_GEOMETRY_GATE_FAILED")
        if passed < self.MINIMUM_PASSES:
            reasons.append("STRATEGY_CONFIRMATION_QUORUM_NOT_MET")
        state: EvidenceState = "PASS" if passed >= self.MINIMUM_PASSES and not reasons else "FAIL"

        canonical = {
            "policy_version": self.VERSION,
            "venue": venue, "product": product, "symbol": symbol,
            "timeframe": timeframe, "direction": direction,
            "checks": [
                {
                    "name": c.name, "state": c.state, "evidence_ref": c.evidence_ref,
                    "evidence_sha256": c.evidence_sha256, "provider": c.provider,
                    "provider_version": c.provider_version, "observed_at": c.observed_at.isoformat(),
                }
                for c in sorted(checks, key=lambda item: item.name)
            ],
        }
        digest = sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return StrategyQualityResultV1(self.VERSION, state, venue, product, symbol, timeframe,
            direction, passed, self.MINIMUM_PASSES, checks,
            tuple(dict.fromkeys(reasons or ("STRATEGY_QUORUM_PASSED",))), digest)
