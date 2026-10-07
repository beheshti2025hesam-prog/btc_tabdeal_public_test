"""Contract tests for the forward collector safety boundary."""

from datetime import datetime, timezone

import pytest

from forward.collector_adapter_v1 import ForwardCollectorAdapterV1


def _observation():
    return {
        "symbol": "BTC_USDT",
        "price": 100.0,
        "amount": 0.01,
        "side": "buy",
        "observed_at": datetime.now(timezone.utc),
        "sequence": 1,
    }


def test_adapter_is_disabled_by_default():
    adapter = ForwardCollectorAdapterV1()
    with pytest.raises(RuntimeError):
        adapter.accept([_observation()])


def test_enabled_adapter_preserves_sequence_identity():
    adapter = ForwardCollectorAdapterV1(enabled=True)
    result = adapter.accept([_observation()])
    assert len(result) == 1
    assert result[0].sequence == 1
    assert result[0].symbol == "BTC_USDT"
