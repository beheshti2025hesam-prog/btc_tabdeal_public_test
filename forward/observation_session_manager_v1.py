"""Forward observation session manager.

Creates immutable, uniquely identified observation sessions. It is deliberately
local and deterministic: no network, no execution, no historical inputs.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl, hashlib, json, os, uuid
from pathlib import Path

@dataclass(frozen=True)
class ObservationSessionV1:
    run_id: str
    started_at: str
    policy_id: str
    policy_version: str
    symbol: str
    timeframe: str
    source: str
    mode: str = "OBSERVATION_ONLY"
    decision_mode: str = "NO_TRADE_ONLY"
    execution_enabled: bool = False
    historical_inputs_allowed: bool = False

    def record(self) -> dict:
        return {
            "run_id": self.run_id, "started_at": self.started_at,
            "policy_id": self.policy_id, "policy_version": self.policy_version,
            "symbol": self.symbol, "timeframe": self.timeframe, "source": self.source,
            "mode": self.mode, "decision_mode": self.decision_mode,
            "execution_enabled": False, "historical_inputs_allowed": False,
        }

    def digest(self) -> str:
        raw=json.dumps(self.record(),sort_keys=True,separators=(",",":"))
        return hashlib.sha256(raw.encode()).hexdigest()

class ObservationSessionManagerV1:
    def __init__(self, *, policy_id: str, policy_version: str, symbol="BTC_USDT",
                 timeframe="15m", source="tabdeal_ws_forward_v1"):
        self.policy_id=policy_id; self.policy_version=policy_version
        self.symbol=symbol; self.timeframe=timeframe; self.source=source

    def start(self, *, started_at: datetime) -> ObservationSessionV1:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError("started_at must be timezone-aware")
        if self.symbol != "BTC_USDT" or self.timeframe != "15m":
            raise ValueError("unsupported observation scope")
        if not self.source.startswith("tabdeal_"):
            raise ValueError("unsupported observation source")
        ts=started_at.astimezone(timezone.utc)
        run_id=f"OBS-{ts.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
        return ObservationSessionV1(run_id=run_id,started_at=ts.isoformat(),
            policy_id=self.policy_id,policy_version=self.policy_version,
            symbol=self.symbol,timeframe=self.timeframe,source=self.source)

    def write_once(self, session: ObservationSessionV1, path: str|Path) -> str:
        """Append one immutable session record, rejecting duplicate run IDs."""
        target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
        payload=session.record(); payload["session_digest"]=session.digest()
        line=json.dumps(payload,sort_keys=True,separators=(",",":"))+"\n"
        lock_path=target.with_name(target.name+".lock")
        with lock_path.open("a+",encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                if target.exists():
                    with target.open("r",encoding="utf-8") as handle:
                        for raw in handle:
                            if not raw.strip():
                                continue
                            existing=json.loads(raw)
                            if existing.get("run_id") == session.run_id:
                                raise ValueError("duplicate observation session")
                with target.open("a",encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
                    os.fsync(handle.fileno())
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        return payload["session_digest"]
