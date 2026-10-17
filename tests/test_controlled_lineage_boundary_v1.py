from datetime import datetime, timezone
import hashlib

import pytest

from forward.tabdeal_readonly_adapter_v1 import parse_trade_frame
from forward.sequence_candle_integration_v1 import SequenceAwareCandleIngestionV1

AS_OF = datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)


def frame(sequence_marker=True, sequence="0007"):
    value = {
        "type": "trade",
        "symbol": "BTC_USDT",
        "price": "65000.25",
        "amount": "0.01",
        "side": "buy",
        "timestamp": "2026-10-13T19:59:00Z",
    }
    if sequence_marker:
        value["sequence"] = sequence
    return value


@pytest.mark.parametrize("sequence", ["0007", 7, 6, "opaque-id"])
def test_real_adapter_preserves_sequence_as_opaque_and_carries_lineage(sequence):
    raw = '{"type":"trade","symbol":"BTC_USDT","price":"65000.25","amount":"0.01","side":"buy","timestamp":"2026-10-13T19:59:00Z","sequence":' + (
        '"' + sequence + '"' if isinstance(sequence, str) else str(sequence)
    ) + '}'
    parsed = parse_trade_frame(
        frame(sequence=sequence), as_of=AS_OF, raw_payload=raw,
        session_id="sess-test", run_id="run-test",
    )
    assert parsed["sequence"] == sequence
    assert parsed["sequence_semantics"] == "UNKNOWN_OPAQUE"
    assert parsed["session_id"] == "sess-test"
    assert parsed["run_id"] == "run-test"
    assert parsed["raw_payload_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_adapter_allows_missing_opaque_sequence_but_marks_it_unknown():
    parsed = parse_trade_frame(frame(sequence_marker=False), as_of=AS_OF)
    assert parsed["sequence"] is None
    assert parsed["sequence_semantics"] == "UNKNOWN_OPAQUE"


@pytest.mark.parametrize("sequence", ["0007", 7, 6, None])
def test_actual_candle_consumer_fails_closed_before_candle_use(sequence):
    parsed = parse_trade_frame(
        frame(sequence_marker=sequence is not None, sequence=sequence),
        as_of=AS_OF,
        raw_payload='{"captured":"raw"}',
        session_id="sess-test",
        run_id="run-test",
    )
    result = SequenceAwareCandleIngestionV1().ingest([parsed], as_of=AS_OF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "UNKNOWN_SEQUENCE_SEMANTICS"


def test_raw_payload_hash_mismatch_fails_closed_before_candle_use():
    parsed = parse_trade_frame(
        frame(), as_of=AS_OF, raw_payload='{"captured":"raw"}',
        session_id="sess-test", run_id="run-test",
    )
    parsed["raw_payload"] = '{"captured":"tampered"}'
    result = SequenceAwareCandleIngestionV1().ingest([parsed], as_of=AS_OF)
    assert result.safe_for_decision is False
    assert result.candles == ()
    assert result.events[-1].reason == "RAW_PAYLOAD_DIGEST_MISMATCH"


def test_lineage_ids_are_never_silently_filled_when_not_supplied():
    parsed = parse_trade_frame(frame(), as_of=AS_OF)
    assert "session_id" not in parsed
    assert "run_id" not in parsed
