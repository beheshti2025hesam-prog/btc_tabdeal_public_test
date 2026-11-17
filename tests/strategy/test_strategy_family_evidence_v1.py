from datetime import datetime, timezone
import json

import pytest

import importlib

try:
    family_evidence_module = importlib.import_module("forward.strategy_family_evidence_v1")
    build_range_family_evidence = getattr(family_evidence_module, "build_range_family_evidence", None)
except ImportError:
    family_evidence_module = None
    build_range_family_evidence = None


def test_range_family_evidence_builder_is_exposed():
    assert callable(build_range_family_evidence)


def _requires_builder(test):
    return pytest.mark.skipif(build_range_family_evidence is None, reason="family evidence builder not implemented yet")(test)


AS_OF = 1_800_000_000 + 240 * 14_400
OBS = datetime.fromtimestamp(AS_OF, timezone.utc)
NOW_MS = (AS_OF + 2) * 1000
CHECK_NAMES = (
    "candidate_valid",
    "range_persistence",
    "range_boundary_location",
    "reversal_trigger",
    "direction_regime_alignment",
    "directional_flow_confirmation",
    "structure_confirmation",
    "cost_adjusted_geometry",
)


def make_rows(timeframe, *, direction="LONG", as_of=AS_OF, count=240):
    seconds = {"15m": 900, "1h": 3600, "4h": 14400}[timeframe]
    rows = []
    for index in range(count):
        opened = as_of - count * seconds + index * seconds
        open_price = close = 101.0
        high, low = 101.5, 100.5
        if timeframe == "15m":
            if index == count - 49:
                high, low = 105.0, 100.0
            elif index == count - 48:
                high, low = 102.0, 97.0
            if direction == "LONG":
                if index == count - 2:
                    open_price, high, low, close = 101.0, 101.5, 96.8, 97.0
                elif index == count - 1:
                    open_price, high, low, close = 97.5, 101.0, 96.5, 98.0
            else:
                if index == count - 2:
                    open_price, high, low, close = 104.0, 105.2, 103.5, 105.0
                elif index == count - 1:
                    open_price, high, low, close = 104.5, 105.5, 103.5, 104.0
        rows.append({
            "schema": "hes_global_candle_v1",
            "source": "gateio_public_spot",
            "symbol": "BTC_USDT",
            "timeframe": timeframe,
            "open_time": opened,
            "close_time": opened + seconds,
            "open": str(open_price),
            "high": str(high),
            "low": str(low),
            "close": str(close),
            "volume": "1.0",
            "quote_volume": str(close),
            "closed": True,
            "observed_at": datetime.fromtimestamp(as_of + 2, timezone.utc).isoformat(),
        })
    return rows


def make_frames(direction="LONG", *, as_of=AS_OF):
    return {tf: make_rows(tf, direction=direction, as_of=as_of) for tf in ("15m", "1h", "4h")}


def build(frames=None, *, direction="LONG", observed_at=OBS, now_ms=NOW_MS, source="gateio_public_spot", symbol="BTC_USDT"):
    return build_range_family_evidence(
        frames=make_frames(direction) if frames is None else frames,
        source=source,
        symbol=symbol,
        observed_at=observed_at,
        now_ms=now_ms,
    )


@_requires_builder
def test_range_family_evidence_emits_long_sweep_reclaim_and_eight_independent_checks():
    result = build()

    assert result.status == "READY"
    assert result.candidate["state"] == "CANDIDATE_LONG"
    assert result.candidate["direction"] == "LONG"
    assert result.candidate["regime"] == "RANGE"
    assert result.candidate["source"] == "gateio_public_spot"
    assert result.candidate["symbol"] == "BTC_USDT"
    assert result.candidate["timeframe"] == "15m"
    assert result.candidate["evidence_sha256"] == result.evidence_sha256
    assert len(result.evidence_sha256) == 64
    assert tuple(check.name for check in result.checks) == CHECK_NAMES
    assert all(check.state == "PASS" and check.observed_at == OBS for check in result.checks)
    flow_check = next(check for check in result.checks if check.name == "directional_flow_confirmation")
    assert "MFI14_BASE_VOLUME" in flow_check.evidence_ref
    assert "TAKER_BUY_UNAVAILABLE" in flow_check.evidence_ref
    assert result.cost_model_status == "ASSUMPTION_BASED"
    assert result.execution_enabled is False and result.orders_placed is False
    assert result.candidate_generation_authorized is False


@_requires_builder
def test_range_family_evidence_emits_short_sweep_reclaim():
    result = build(direction="SHORT")

    assert result.status == "READY"
    assert result.candidate["state"] == "CANDIDATE_SHORT"
    assert result.candidate["direction"] == "SHORT"
    assert len(result.checks) == 8
    assert all(check.state == "PASS" for check in result.checks)


@_requires_builder
def test_range_family_evidence_is_causal_and_ignores_future_candles_and_one_minute_data():
    frames = make_frames()
    future = dict(frames["15m"][-1])
    future["open_time"] = AS_OF
    future["close_time"] = AS_OF + 900
    future["open"] = "98.0"
    future["high"] = "999999.0"
    future["low"] = "1.0"
    future["close"] = "98.0"
    future["observed_at"] = datetime.fromtimestamp(AS_OF + 902, timezone.utc).isoformat()
    frames["15m"] = frames["15m"] + [future]
    frames["1m"] = [{"source": "not-used", "symbol": "NOT_USED", "high": "999999"}]
    result = build(frames=frames, now_ms=(AS_OF + 902) * 1000)
    baseline = build()

    assert result.status == "READY"
    assert result.candidate["direction"] == baseline.candidate["direction"]
    assert result.evidence_sha256 == baseline.evidence_sha256


@_requires_builder
def test_range_family_evidence_fails_closed_on_source_scope_mismatch():
    result = build(source="binance_public_spot")

    assert result.status == "BLOCKED"
    assert result.candidate is None
    assert result.blocked_reasons


@_requires_builder
def test_range_family_evidence_fails_closed_on_missing_timeframe():
    frames = make_frames()
    del frames["1h"]
    result = build(frames=frames)

    assert result.status == "BLOCKED"
    assert "MISSING_REQUIRED_TIMEFRAME:1h" in result.blocked_reasons


@_requires_builder
def test_range_family_evidence_fails_closed_on_observed_gap():
    frames = make_frames()
    del frames["1h"][100]
    result = build(frames=frames)

    assert result.status == "BLOCKED"
    assert "SOURCE_GAP:1h" in result.blocked_reasons


@_requires_builder
def test_range_family_evidence_fails_closed_when_eligible_row_was_observed_after_setup_window():
    frames = make_frames()
    frames["4h"][-1]["observed_at"] = datetime.fromtimestamp(AS_OF + 61, timezone.utc).isoformat()
    result = build(frames=frames, now_ms=(AS_OF + 120) * 1000)

    assert result.status == "BLOCKED"
    assert "EVIDENCE_OBSERVED_AFTER_SETUP_WINDOW:4h" in result.blocked_reasons


@_requires_builder
def test_range_family_evidence_fails_closed_on_stale_15m_feed():
    result = build(now_ms=(AS_OF + 31 * 60) * 1000)

    assert result.status == "BLOCKED"
    assert "SETUP_15M_CANDLE_STALE" in result.blocked_reasons


@_requires_builder
def test_range_family_evidence_does_not_confirm_when_htf_adx_is_trending():
    frames = make_frames()
    for index, row in enumerate(frames["1h"]):
        value = 100.0 + index * 0.5
        row.update(open=str(value - 0.2), high=str(value + 0.5), low=str(value - 0.5), close=str(value))
    result = build(frames=frames)

    assert result.status == "NO_CANDIDATE"
    assert result.candidate is None
    assert "TREND_STRENGTH_TOO_HIGH" in result.blocked_reasons


@_requires_builder
def test_range_family_evidence_binds_only_the_eligible_source_windows():
    baseline = build()
    frames = make_frames()
    frames["15m"][-1]["quote_volume"] = "999999999.0"
    changed = build(frames=frames)

    assert baseline.status == "READY" and changed.status == "READY"
    assert baseline.evidence_sha256 != changed.evidence_sha256


@_requires_builder
def test_range_family_pipeline_dispatches_research_confirmation_but_global_risk_gate_vetoes(monkeypatch):
    import forward.strategy_gate_pipeline_v1 as pipeline
    from forward.strategy_policy_v2 import PolicyDecision, POLICY_VERSION

    def fake_structure(rows, observed_at):
        return {
            "observed_at": observed_at.isoformat(),
            "status": "OBSERVED",
            "regime": "RANGE",
            "labels": ["HH", "LL", "LH", "HL"],
            "swing_count": 8,
            "last_swing_high": "105",
            "last_swing_low": "97",
            "events": [],
            "policy_note": "test-only range regime fixture",
        }

    monkeypatch.setattr(pipeline, "inspect_structure", fake_structure)
    proposal = PolicyDecision(
        POLICY_VERSION, "NO_TRADE", "NONE", 0, None, None, None, None,
        ("NO_TRADE",), {"policy": "NO_TRADE"},
    )
    result = pipeline.evaluate_gate_evidence(
        proposal=proposal,
        rows_15m=make_frames()["15m"],
        frames=make_frames(),
        source="gateio_public_spot",
        symbol="BTC_USDT",
        observed_at=OBS,
        now_ms=NOW_MS,
    )

    assert result["strategy_family_route"]["family_id"] == "range_mean_reversion"
    assert result["strategy_family_evidence"]["status"] == "READY"
    assert result["strategy_family_candidate"]["state"] == "CANDIDATE_LONG"
    assert result["strategy_family_confirmation"]["state"] == "RESEARCH_CONFIRMED_LONG"
    assert result["strategy_family_confirmation"]["confirmation_authority"] is False
    assert result["confirmation"]["state"] == "UNCONFIRMED"
    assert result["risk"]["state"] == "RISK_REJECTED"
    risk_checks = {check["name"]: check["state"] for check in result["risk"]["checks"]}
    assert risk_checks["confirmation_valid"] == "FAIL"
    assert risk_checks["risk_reward_gate_passed"] == "FAIL"
    assert result["final_decision"] == "NO_TRADE"
    assert result["execution_enabled"] is False and result["orders_placed"] is False
    assert result["strategy_family_context_status"] == "VERIFIED_EVIDENCE_ONLY_NOT_AUTHORIZED"
    assert result["strategy_family_context"]["family_id"] == "range_mean_reversion"
    assert result["strategy_family_context"]["candidate_generation_authorized"] is False
    json.dumps(result["strategy_family_evidence"])
    json.dumps(result["strategy_family_candidate"])
    json.dumps(result["strategy_family_confirmation"])
    json.dumps(result["strategy_family_context"])
