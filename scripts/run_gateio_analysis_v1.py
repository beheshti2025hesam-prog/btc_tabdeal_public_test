#!/usr/bin/env python3
"""Read validated Gate.io candles, compute observations, and invoke existing fail-closed decision engine.

Read-only: this script has no exchange execution client and cannot place orders.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from forward.global_market_data_reader_v1 import load_market_input
from forward.signal_engine_v1 import (
    MarketInput, StructureState, ConfirmationState, RiskState,
    ForwardSignalEngineV1,
)
from scripts.analyze_gateio_snapshot_v1 import snapshot

def run(root: Path=ROOT) -> dict:
    source=load_market_input(root=root)
    # Keep feed-observation time separate from candle event time and decision time.
    # The reader has already required an explicit timezone-aware observed_at on
    # every candle and rejected timestamps too far in the future.
    observed=datetime.fromisoformat(source["observed_at"].replace("Z","+00:00"))
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("MARKET_OBSERVATION_TIME_MUST_BE_TIMEZONE_AWARE")
    latest_close=int(source["timeframes"]["15m"][-1]["close_time"])
    features={tf:snapshot(tf,rows) for tf,rows in source["timeframes"].items()}
    market=MarketInput(
        observed_at=observed,
        symbol="BTC_USDT",
        timeframe="15m",
        values={"source":source["source"],"multi_timeframe":features},
    )
    # No strategy policy has been approved in this integration. Explicitly
    # supply unknown structure, unconfirmed confirmation and a closed risk gate.
    result=ForwardSignalEngineV1().evaluate(
        market=market,
        structure=StructureState(state="UNKNOWN",values={"source":"not_yet_policy_backed"}),
        candidate=None,
        confirmation=ConfirmationState(state="NOT_CONFIGURED",reason_codes=("VERSIONED_CONFIRMATION_POLICY_MISSING",)),
        risk=RiskState(state="RISK_NOT_APPROVED",reason_codes=("RISK_APPROVAL_NOT_GRANTED",)),
    )
    output={
        "schema":"hes_gateio_analysis_decision_v1",
        "observed_at":observed.isoformat(),
        "decision_at":datetime.now(timezone.utc).isoformat(),
        "latest_closed_candle_at":datetime.fromtimestamp(latest_close,timezone.utc).isoformat(),
        "source":source["source"],
        "symbol":market.symbol,
        "timeframe":market.timeframe,
        "market_features":features,
        "decision":{
            "decision":result.decision,
            "direction":result.direction,
            "market_regime":result.market_regime,
            "signal_state":result.signal_state,
            "confirmation_state":result.confirmation_state,
            "risk_state":result.risk_state,
            "no_trade_reason":result.no_trade_reason,
        },
        "execution_enabled":False,
        "orders_placed":False,
    }
    dest=Path(root)/"data/forward/gateio_analysis_decision_v1.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(output,indent=2)+"\n",encoding="utf-8")
    return output

if __name__=="__main__":
    result=run()
    print(json.dumps(result,indent=2))
