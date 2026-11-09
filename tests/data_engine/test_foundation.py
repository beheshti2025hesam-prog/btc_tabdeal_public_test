"""
Focused Data Foundation contract tests for the main-integration slice.
"""
from datetime import datetime, timezone
from core.data_engine.engine import DataEngine
from core.data_engine.integrity import IntegrityAudit
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.models.trade import CanonicalTrade

def row(ts="2026-09-20T10:00:00Z", seq="1", price="100000", amount="0.001", side="buy"):
    return {"symbol":"BTC_USDT","price":price,"amount":amount,"side":side,"updated":ts,"sequence":seq}

def test_validator_hard_boundaries():
    v=RawDataValidator()
    assert v.validate_row(row()) == []
    assert "Invalid side" in v.validate_row(row(side="hold"))
    assert v.validate_row(row(seq="0")) == []
    assert v.validate_row(row(seq="opaque-venue-token")) == []
    assert "Timestamp must be timezone-aware" in v.validate_row(row(ts="2026-09-20T10:00:00"))

def test_normalizer_is_venue_agnostic():
    n=RawDataNormalizer(source="stream", exchange="example")
    t=n.normalize_row(row(seq="42"))
    assert isinstance(t, CanonicalTrade)
    assert t.exchange == "example" and t.sequence == "42"
    assert t.timestamp == datetime(2026,9,20,10,0,tzinfo=timezone.utc)

def test_integrity_does_not_infer_tabdeal_sequence_gaps_or_identity():
    def t(seq, seconds, price=100000):
        return CanonicalTrade(f"e{seq}{seconds}","test","tabdeal","BTC_USDT",price,0.001,"buy",datetime(2026,9,20,10,0,seconds,tzinfo=timezone.utc),seq)
    report=IntegrityAudit().audit([t(10,0),t(12,1,100001),t(12,2)])["groups"][("tabdeal","BTC_USDT")]
    assert report["sequence_semantics_status"] == "UNKNOWN"
    assert report["sequence_ordering_status"] == "UNKNOWN"
    assert report["sequence_identity_status"] == "UNKNOWN"
    assert report["sequence_gap_count"] is None
    assert report["sequence_gap_total"] is None
    assert report["duplicate_sequence_count"] is None
    assert report["min_sequence_value"] is None
    assert report["max_sequence_value"] is None
    assert report["repeated_sequence_value_count"] == 1
    assert report["duplicate_event_id_count"] == 0

def test_reader_is_read_only_and_discovers_archives(tmp_path):
    active=tmp_path/"trades.csv"
    active.write_text("symbol,price,amount,side,updated,sequence\n"+ "BTC_USDT,100000,0.001,buy,2026-09-20T10:00:00Z,1\n", encoding="utf-8")
    archive=tmp_path/"archive"; archive.mkdir()
    (archive/"z.csv").write_text("symbol,price,amount,side,updated,sequence\n", encoding="utf-8")
    reader=RawDataReader(str(active),str(archive))
    before=active.read_text(encoding="utf-8")
    assert reader.discover_files()==[str(active),str(archive/"z.csv")]
    list(reader.read_all())
    assert active.read_text(encoding="utf-8")==before

def test_engine_is_deterministic_and_deduplicates():
    class R:
        def read_all(self):
            yield row(ts="2026-09-20T10:00:02Z",seq="2")
            yield row(ts="2026-09-20T10:00:01Z",seq="1")
            yield row(ts="2026-09-20T10:00:01Z",seq="1")
    result=DataEngine(reader=R()).load()
    assert [t.sequence for t in result]==["1","2"]


def test_normalizer_preserves_sequence_as_opaque_text_and_allows_missing():
    n = RawDataNormalizer(source="stream", exchange="tabdeal")
    assert n.normalize_row(row(seq="007")).sequence == "007"
    assert n.normalize_row(row(seq="opaque-venue-token")).sequence == "opaque-venue-token"
    missing = row()
    missing.pop("sequence")
    assert RawDataValidator().validate_row(missing) == []
    assert n.normalize_row(missing).sequence is None


def test_engine_does_not_conflate_distinct_payloads_sharing_opaque_sequence():
    class R:
        def read_all(self):
            yield row(ts="2026-09-20T10:00:01Z", seq="7", price="100000")
            yield row(ts="2026-09-20T10:00:02Z", seq="7", price="100001")
            yield row(ts="2026-09-20T10:00:03Z", seq="007", price="100002")

    result = DataEngine(reader=R()).load()
    assert len(result) == 3
    assert [trade.sequence for trade in result] == ["7", "7", "007"]
