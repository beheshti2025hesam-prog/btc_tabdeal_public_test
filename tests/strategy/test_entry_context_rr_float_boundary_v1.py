import pytest

from forward.precision_entry_engine_v1 import _valid_context
from forward.strategy_entry_context_v1 import build_entry_context, verify_entry_context


def _gate(direction):
    return {
        "risk": {"state": "RISK_APPROVED"},
        "confirmation": {"state": f"CONFIRMED_{direction}"},
        "structure": {
            "status": "OBSERVED",
            "regime": "UPTREND" if direction == "LONG" else "DOWNTREND",
        },
        "strategy_run_provenance": {
            "run_id": "HESV2-test-run",
            "service_name": "strategy_policy_v2_forward_evaluator",
            "code_release_id": "test-release",
            "run_manifest_sha256": "a" * 64,
        },
        "execution_enabled": False,
        "orders_placed": False,
    }


@pytest.mark.parametrize(
    "direction,entry,stop,target",
    [
        # Real HES candidate geometry: binary floating point evaluates this as
        # 2.9999999999999387 even though the strategy generated exactly 3R.
        ("SHORT", 73584.0, 73821.24645, 72872.26065),
        ("LONG", 100.0, 90.0, 130.0),
    ],
)
def test_exact_three_r_context_survives_build_verify_and_precision_engine(
    direction, entry, stop, target
):
    evidence = _gate(direction)
    context = build_entry_context(
        source="gateio_public_spot",
        symbol="BTC_USDT",
        candidate_time=1794460500,
        policy_version="hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
        direction=direction,
        entry=entry,
        stop=stop,
        target=target,
        gate_evidence=evidence,
    )

    assert context["planned_rr"] == 3.0
    assert context["strategy_run_provenance"]["run_id"] == "HESV2-test-run"
    assert verify_entry_context(
        context,
        gate_evidence=evidence,
        now_s=1794460501,
        expected_direction=direction,
    ) == (True, None)

    values, error = _valid_context(
        context, direction=direction, now_s=1794460501, min_rr=3.0
    )
    assert error is None
    assert values is not None
    assert values["worst_case_rr"] == 3.0


def test_materially_sub_three_r_context_remains_rejected():
    evidence = _gate("SHORT")
    with pytest.raises(ValueError, match="ENTRY_CONTEXT_RR_BELOW_MINIMUM"):
        build_entry_context(
            source="gateio_public_spot",
            symbol="BTC_USDT",
            candidate_time=1794460500,
            policy_version="hes-btcusdt-mtf-confirmed-breakout-v2.0.0",
            direction="SHORT",
            entry=73584.0,
            stop=73821.24645,
            target=72872.26165,
            gate_evidence=evidence,
        )
