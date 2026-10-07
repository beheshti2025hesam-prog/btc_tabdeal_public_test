"""Immutable identity for forward observation snapshots."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json


@dataclass(frozen=True)
class ObservationSnapshotIdentity:
    snapshot_id: str
    forward_run_id: str
    observed_at: str
    symbol: str
    timeframe: str
    digest: str


class ObservationSnapshotIdentityV1:
    def create(self, *, forward_run_id: str, observed_at: datetime, symbol: str, timeframe: str, payload: dict) -> ObservationSnapshotIdentity:
        if not forward_run_id:
            raise ValueError("forward_run_id required")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("timezone-aware observed_at required")
        if observed_at > datetime.now(timezone.utc):
            raise ValueError("future observed_at forbidden")
        if symbol != "BTC_USDT" or timeframe != "15m":
            raise ValueError("unsupported scope")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload required")
        canonical=json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=False)
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        snapshot_id=f"{forward_run_id}:{observed_at.astimezone(timezone.utc).isoformat()}:{digest[:16]}"
        return ObservationSnapshotIdentity(snapshot_id,forward_run_id,observed_at.astimezone(timezone.utc).isoformat(),symbol,timeframe,digest)
