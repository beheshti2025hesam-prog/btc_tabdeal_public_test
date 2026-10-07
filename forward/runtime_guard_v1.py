"""Runtime guards for the forward-only boundary.

These guards are intentionally policy-neutral. They prevent accidental use of
historical populations and future outcomes at the runtime boundary.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass(frozen=True)
class RuntimeContext:
    source: str
    observed_at: str
    forward_run_id: str

def validate_context(ctx: RuntimeContext) -> None:
    if not ctx.forward_run_id.strip():
        raise ValueError("forward_run_id is required")
    if ctx.source.lower() in {"winner","survivor","historical","legacy"}:
        raise ValueError("historical source is forbidden in forward runtime")
    dt=datetime.fromisoformat(ctx.observed_at.replace("Z","+00:00"))
    if dt.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    if dt.tzinfo.utcoffset(dt) is None:
        raise ValueError("observed_at must be timezone-aware")

def validate_decision_record(record: dict) -> None:
    required=("event_id","observed_at","symbol","timeframe","decision","evidence_source")
    missing=[k for k in required if record.get(k) in (None,"")]
    if missing:
        raise ValueError("missing required fields: "+",".join(missing))
    if record["decision"] not in {"LONG","SHORT","NO_TRADE"}:
        raise ValueError("invalid decision")
    if record.get("outcome") not in (None,"OPEN"):
        raise ValueError("new decision cannot contain a closed future outcome")
