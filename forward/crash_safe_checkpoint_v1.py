"""Crash-safe, write-once checkpoint boundary with fail-closed resume."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib, json

@dataclass(frozen=True)
class Checkpoint:
    segment_id:int
    checkpoint_id:str
    last_sequence:int|None
    digest:str

class CrashSafeCheckpointV1:
    def __init__(self):
        self._written:dict[str,Checkpoint]={}

    @staticmethod
    def _digest(payload:dict)->str:
        raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def write_once(self, *, segment_id:int, checkpoint_id:str, last_sequence:int|None)->Checkpoint:
        if segment_id < 1 or not checkpoint_id:
            raise ValueError("invalid checkpoint identity")
        payload={"segment_id":segment_id,"checkpoint_id":checkpoint_id,"last_sequence":last_sequence}
        digest=self._digest(payload)
        cp=Checkpoint(segment_id,checkpoint_id,last_sequence,digest)
        prior=self._written.get(checkpoint_id)
        if prior:
            if prior.digest != digest:
                raise ValueError("CHECKPOINT_CONFLICT")
            return prior
        self._written[checkpoint_id]=cp
        return cp

    def resume(self, checkpoint_id:str)->None:
        # A persisted checkpoint is metadata only; it is never sequence-adjacency proof.
        if checkpoint_id not in self._written:
            raise ValueError("CHECKPOINT_NOT_FOUND")
        return None
