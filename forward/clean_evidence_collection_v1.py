"""Clean forward evidence boundary; observation-only and forward-only."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ForwardEvidenceRecord:
    forward_run_id: str
    event_id: str
    observed_at: datetime
    symbol: str
    timeframe: str
    status: str
    source: str

    def __post_init__(self) -> None:
        if not self.forward_run_id.strip():
            raise ValueError("missing forward_run_id")
        if not self.event_id.strip():
            raise ValueError("missing event_id")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.observed_at > datetime.now(timezone.utc):
            raise ValueError("future observed_at")
        if self.symbol != "BTC_USDT":
            raise ValueError("unsupported symbol")
        if self.timeframe != "15m":
            raise ValueError("unsupported timeframe")
        if not self.source.startswith("tabdeal_ws_forward_v1"):
            raise ValueError("non-forward source")
        forbidden = {"winner", "survivor", "legacy", "historical"}
        if any(x in self.source.lower() for x in forbidden):
            raise ValueError("historical source forbidden")
        if self.status not in {
            "CANDLE_CLOSED_OBSERVED",
            "NO_TRADE_DATA_GAP",
            "NO_TRADE_UNSAFE",
        }:
            raise ValueError("invalid forward evidence status")
