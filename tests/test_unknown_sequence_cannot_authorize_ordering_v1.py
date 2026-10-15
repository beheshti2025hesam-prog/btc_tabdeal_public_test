import json

import pytest

from forward.signed_sequence_contract_gate_v1 import validate_sequence_contract_payload


def test_unknown_sequence_semantics_cannot_authorize_ordering():
    payload = {
        "schema": "hes_sequence_contract_v1",
        "venue": "tabdeal",
        "product": "futures_margin",
        "endpoint": "special_margin/broadcast/",
        "channel": "trade_broadcast",
        "message_type": "trade",
        "field_path": "trade.sequence",
        "scope": "tabdeal:futures:BTC_USDT",
        "protocol_version": "unknown",
        "semantic_class": "unknown",
        "capabilities": {
            "exact_replay_dedup": True,
            "event_id_dedup": False,
            "ordered_within_scope": True,
            "contiguous_within_scope": False,
            "gap_detectable": False,
            "cross_reconnect": False,
        },
    }

    with pytest.raises(ValueError, match="unknown semantic_class cannot authorize"):
        validate_sequence_contract_payload(
            json.dumps(payload).encode("utf-8"),
            market_scope="tabdeal:futures:BTC_USDT",
        )
