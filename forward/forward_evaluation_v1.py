"""Descriptive forward-only evaluation primitives.

This module measures already-recorded decisions/outcomes. It never changes
decisions, tunes parameters, or imports historical populations.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class EvaluationSummary:
    decision_count: int
    long_count: int
    short_count: int
    no_trade_count: int
    closed_trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float | None
    expectancy: float | None
    realized_rr: float | None

def evaluate(records: Iterable[dict]) -> EvaluationSummary:
    rows=list(records)
    decisions=[r for r in rows if r.get("decision") in {"LONG","SHORT","NO_TRADE"}]
    trades=[r for r in decisions if r.get("decision") in {"LONG","SHORT"}]
    closed=[r for r in trades if r.get("outcome") in {"WIN","LOSS","BREAKEVEN"}]
    wins=sum(r["outcome"]=="WIN" for r in closed)
    losses=sum(r["outcome"]=="LOSS" for r in closed)
    bes=sum(r["outcome"]=="BREAKEVEN" for r in closed)
    rr=[float(r["realized_rr"]) for r in closed if r.get("realized_rr") is not None]
    return EvaluationSummary(
        decision_count=len(decisions),
        long_count=sum(r["decision"]=="LONG" for r in decisions),
        short_count=sum(r["decision"]=="SHORT" for r in decisions),
        no_trade_count=sum(r["decision"]=="NO_TRADE" for r in decisions),
        closed_trade_count=len(closed),
        win_count=wins,
        loss_count=losses,
        breakeven_count=bes,
        win_rate=(wins/len(closed) if closed else None),
        expectancy=(sum(rr)/len(rr) if rr else None),
        realized_rr=(sum(rr)/len(rr) if rr else None),
    )
