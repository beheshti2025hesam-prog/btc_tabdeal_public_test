import json
from datetime import datetime, timezone
import pytest

from forward.tabdeal_transport_v1 import TabdealReadOnlyTransportV1

ASOF = datetime(2026, 10, 7, 7, 0, tzinfo=timezone.utc)


class FakeWS:
    def __init__(self, url, on_open, on_message):
        self.url = url
        self.on_open = on_open
        self.on_message = on_message
        self.sent = []
        self.closed = False

    def send(self, value):
        self.sent.append(value)

    def close(self):
        self.closed = True

    def run_forever(self, **kwargs):
        self.on_open(self)
        self.on_message(self, json.dumps({"trade": {
            "symbol": "BTC_USDT", "price": "100", "amount": "1",
            "side_name": "buy", "sequence": 1,
            "updated": "2026-10-07T06:59:00+00:00"
        }}))
        self.on_message(self, json.dumps({"order": {"x": 1}}))
        self.on_message(self, json.dumps({"trade": {
            "symbol": "ETH_USDT", "price": "100", "amount": "1",
            "side_name": "buy", "sequence": 2,
            "updated": "2026-10-07T06:59:01+00:00"
        }}))


def test_transport_only_handoffs_records_and_classifies_frames():
    out = []
    holder = {}
    def factory(*args, **kwargs):
        holder["ws"] = FakeWS(*args, **kwargs)
        return holder["ws"]

    t = TabdealReadOnlyTransportV1(
        as_of_provider=lambda: ASOF,
        on_record=out.append,
        ws_factory=factory,
        max_runtime_seconds=1,
    )
    t.run_once()
    assert holder["ws"].sent == ["BTC_USDT"]
    assert out[0]["source"] == "tabdeal_ws_forward_v1"
    assert t.records_emitted == 1
    assert t.rejected == 1
    assert t.ignored_non_trade == 1
    assert t.rejection_reasons == ["symbol mismatch"]
    assert t.frames_seen == 3
    assert t.closed is True
    assert t.timed_out is False


def test_transport_rejects_non_positive_runtime():
    with pytest.raises(ValueError, match="positive"):
        TabdealReadOnlyTransportV1(
            as_of_provider=lambda: ASOF,
            on_record=lambda _: None,
            ws_factory=FakeWS,
            max_runtime_seconds=0,
        )


class BlockingWS(FakeWS):
    def run_forever(self, **kwargs):
        self.on_open(self)
        import time
        time.sleep(0.05)


def test_transport_has_bounded_runtime_and_closes_socket():
    holder = {}
    def factory(*args, **kwargs):
        holder["ws"] = BlockingWS(*args, **kwargs)
        return holder["ws"]

    t = TabdealReadOnlyTransportV1(
        as_of_provider=lambda: ASOF,
        on_record=lambda _: None,
        ws_factory=factory,
        max_runtime_seconds=0.01,
    )
    t.run_once()
    assert t.timed_out is True
    assert holder["ws"].closed is True
    assert t.closed is True


def test_transport_rejects_invalid_json_with_reason():
    t = TabdealReadOnlyTransportV1(
        as_of_provider=lambda: ASOF,
        on_record=lambda _: None,
        ws_factory=FakeWS,
    )
    fake = FakeWS("", t._open, t._message)
    t._message(fake, "{bad")
    assert t.rejected == 1
    assert t.rejection_reasons == ["INVALID_JSON"]
