import importlib.util
from datetime import datetime, timezone, timedelta
from pathlib import Path

MODULE = Path(__file__).resolve().parents[2]/"forward/structure_only_no_trade_shadow_v1.py"
spec = importlib.util.spec_from_file_location("structure_only_no_trade_shadow_v1", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def _decision(direction="LONG", regime="UPTREND", stop=95.0):
    return {
        "event_id": "shadow-test",
        "observed_at": "2026-11-12T00:00:11+00:00",
        "decision": "NO_TRADE",
        "proposal_direction": "NONE",
        "gate_evidence": {
            "structure": {
                "regime": regime,
                "last_swing_low": str(stop),
                "last_swing_high": "105.0",
            },
            "confirmation": {"checks": [
                {"name": "candidate_valid", "state": "PASS"},
                {"name": "structural_event_present", "state": "PASS"},
                {"name": "direction_regime_alignment", "state": "FAIL",
                 "evidence_ref": f"proposal_direction:NONE;candidate_direction:{direction};regime:{regime}"},
            ]},
        },
    }

def _candles(count=60, start=None):
    start = int(start or datetime(2026, 11, 12, 0, 1, tzinfo=timezone.utc).timestamp())
    out = []
    for i in range(count):
        op = start + i * 60
        out.append({
            "source": "gateio_public_spot", "symbol": "BTC_USDT", "timeframe": "1m",
            "open_time": op, "close_time": op + 60, "closed": True,
            "open": "100", "high": "100.2", "low": "99.8", "close": "100",
        })
    return out

def test_shadow_replay_uses_next_one_minute_open_and_keeps_incomplete_horizons_pending():
    result = mod.evaluate_structure_only_shadow(_decision(), _candles())
    assert result["status"] == "SHADOW_EVALUATED"
    assert result["entry_price"] == 100.0
    assert result["stop_loss"] == 95.0
    assert result["take_profit"] == 115.0
    assert result["horizons"]["1h"]["outcome_class"] == "SHADOW_TIMEOUT_FLAT"
    assert result["horizons"]["4h"]["outcome_class"] == "SHADOW_PENDING"
    assert result["horizons"]["24h"]["outcome_class"] == "SHADOW_PENDING"
    assert result["execution_enabled"] is False and result["orders_placed"] is False

def test_shadow_same_candle_stop_and_target_is_conservatively_stop():
    candles = _candles()
    candles[0]["high"] = "116"
    candles[0]["low"] = "94"
    result = mod.evaluate_structure_only_shadow(_decision(), candles)
    outcome = result["horizons"]["1h"]
    assert outcome["outcome_class"] == "SHADOW_STOP_HIT"
    assert outcome["ambiguous_same_candle"] is True
    assert outcome["gross_r"] == -1.0

def test_shadow_short_is_price_path_only_and_never_claims_spot_short_economics():
    result = mod.evaluate_structure_only_shadow(_decision("SHORT", "DOWNTREND"), _candles())
    assert result["status"] == "SHADOW_EVALUATED"
    assert result["horizons"]["1h"]["short_economics"] == "NOT_TESTABLE_FROM_SPOT"
    assert result["horizons"]["1h"]["net_sensitivity_long_only"] == {}

def test_shadow_candidate_without_valid_independent_evidence_is_not_scored():
    decision = _decision()
    decision["gate_evidence"]["confirmation"]["checks"][0]["state"] = "FAIL"
    result = mod.evaluate_structure_only_shadow(decision, _candles())
    assert result["status"] == "NO_INDEPENDENT_CANDIDATE"
    assert result["horizons"] == {}

def test_shadow_missing_one_minute_bar_is_data_gap_not_interpolated():
    candles = _candles()
    del candles[20]
    result = mod.evaluate_structure_only_shadow(_decision(), candles)
    assert result["status"] == "SHADOW_EVALUATED"
    assert result["horizons"]["1h"]["outcome_class"] == "SHADOW_DATA_GAP"


def test_shadow_rejects_stop_that_is_already_breached_at_first_executable_open():
    result = mod.evaluate_structure_only_shadow(_decision(stop=101.0), _candles())
    assert result["status"] == "SHADOW_STOP_NOT_ON_LOSS_SIDE"
    assert result["entry_price"] == 100.0
    assert result["stop_loss"] == 101.0
    assert result["horizons"] == {}
