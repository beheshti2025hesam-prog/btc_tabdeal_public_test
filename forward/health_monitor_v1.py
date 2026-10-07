"""Standardized fail-closed health and rejection reason tracking."""
from __future__ import annotations
from dataclasses import dataclass, field

VALID_STATUSES={"LIVE","STALE","NO_DATA","REJECT","DRIFT","ANOMALY","ERROR","RECOVERED"}
@dataclass(frozen=True)
class HealthEvent:
    status:str
    reason_code:str
    detail:str|None=None

@dataclass
class ForwardHealthMonitorV1:
    events:list[HealthEvent]=field(default_factory=list)
    def record(self,status:str,reason_code:str,detail:str|None=None)->HealthEvent:
        if status not in VALID_STATUSES:
            raise ValueError("invalid health status")
        if not reason_code or not reason_code.strip():
            raise ValueError("reason_code required")
        event=HealthEvent(status,reason_code,detail)
        self.events.append(event)
        return event
    def last(self)->HealthEvent|None:
        return self.events[-1] if self.events else None
    def is_safe(self)->bool:
        return bool(self.events) and self.events[-1].status=="LIVE"
    def counts(self)->dict[str,int]:
        out={}
        for e in self.events:
            out[e.reason_code]=out.get(e.reason_code,0)+1
        return out
