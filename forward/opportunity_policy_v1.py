from __future__ import annotations

from .opportunity_detector_v1 import OpportunityCandidate


class OpportunityPolicyV1:
    """Versioned, scope-explicit structural opportunity classifier.

    The default scope is the canonical Gate.io Spot BTC_USDT 15m market-data
    symbol. Callers with a separately approved internal symbol scope must pass
    it explicitly; this policy never silently rewrites venue symbols.
    """

    DEFAULT_ALLOWED_SCOPES = (("BTC_USDT", "15m"),)

    def __init__(self, *, allowed_scopes=DEFAULT_ALLOWED_SCOPES) -> None:
        try:
            scopes = tuple(tuple(scope) for scope in allowed_scopes)
        except TypeError as exc:
            raise ValueError("allowed_scopes must contain explicit symbol/timeframe pairs") from exc
        if (
            not scopes
            or any(
                len(scope) != 2
                or any(not isinstance(value, str) or not value.strip() for value in scope)
                for scope in scopes
            )
            or len(set(scopes)) != len(scopes)
        ):
            raise ValueError("allowed_scopes must contain unique non-empty symbol/timeframe pairs")
        self.allowed_scopes = scopes

    def evaluate(
        self,
        *,
        observed_at,
        symbol,
        timeframe,
        regime,
        structure_labels=(),
        structure_events=(),
    ):
        labels = tuple(structure_labels)
        events = tuple(structure_events)
        if (symbol, timeframe) not in self.allowed_scopes:
            return OpportunityCandidate(
                observed_at, symbol, timeframe, "NO_CANDIDATE", regime,
                labels, events, ("SCOPE_MISMATCH",),
            )
        if regime not in ("UPTREND", "DOWNTREND"):
            return OpportunityCandidate(
                observed_at, symbol, timeframe, "NO_CANDIDATE", regime,
                labels, events, ("REGIME_NOT_DIRECTIONAL",),
            )
        if not events:
            return OpportunityCandidate(
                observed_at, symbol, timeframe, "NO_CANDIDATE", regime,
                labels, events, ("NO_STRUCTURE_EVENT",),
            )
        latest = events[-1]
        if regime == "UPTREND" and latest in ("BOS", "CHOCH", "BOS_BULLISH", "CHOCH_BULLISH", "HH", "HL"):
            return OpportunityCandidate(
                observed_at, symbol, timeframe, "CANDIDATE_LONG", regime,
                labels, events, ("LATEST_STRUCTURAL_EVENT",),
            )
        if regime == "DOWNTREND" and latest in ("BOS", "CHOCH", "BOS_BEARISH", "CHOCH_BEARISH", "LL", "LH"):
            return OpportunityCandidate(
                observed_at, symbol, timeframe, "CANDIDATE_SHORT", regime,
                labels, events, ("LATEST_STRUCTURAL_EVENT",),
            )
        return OpportunityCandidate(
            observed_at, symbol, timeframe, "NO_CANDIDATE", regime,
            labels, events, ("EVENT_DIRECTION_NOT_TRACEABLE",),
        )
