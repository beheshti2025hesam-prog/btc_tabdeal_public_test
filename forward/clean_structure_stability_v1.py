"""Deterministic observation-only structure stability over closed forward candles."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StructureStability:
    status: str
    observations: int
    up_contexts: int
    down_contexts: int
    mixed_contexts: int
    stable_bias: str


class CleanStructureStabilityV1:
    def observe(self, contexts: list[str]) -> StructureStability:
        if not contexts:
            raise ValueError("no structure contexts")
        allowed={"UP_CONTEXT","DOWN_CONTEXT","MIXED_CONTEXT"}
        if any(x not in allowed for x in contexts):
            raise ValueError("invalid structure context")
        up=contexts.count("UP_CONTEXT"); down=contexts.count("DOWN_CONTEXT"); mixed=contexts.count("MIXED_CONTEXT")
        if up==len(contexts): stable="UP_STABLE"
        elif down==len(contexts): stable="DOWN_STABLE"
        else: stable="UNSTABLE"
        return StructureStability("STRUCTURE_STABILITY_OBSERVED",len(contexts),up,down,mixed,stable)
