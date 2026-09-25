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
    assert "Invalid sequence" in v.validate_row(row(seq="0"))
    assert "Timestamp must be timezone-aware" in v.validate_row(row(ts="2026-09-20T10:00:00"))

def test_normalizer_is_venue_agnostic():
    n=RawDataNormalizer(source="stream", exchange="example")
    t=n.normalize_row(row(seq="42"))
    assert isinstance(t, CanonicalTrade)
    assert t.exchange == "example" and t.sequence == 42
    assert t.timestamp == datetime(2026,9,20,10,0,tzinfo=timezone.utc)

def test_integrity_exposes_real_sequence_gap():
    def t(seq, seconds):
        return CanonicalTrade(f"e{seq}{seconds}","test","tabdeal","BTC_USDT",100000,0.001,"buy",datetime(2026,9,20,10,0,seconds,tzinfo=timezone.utc),seq)
    report=IntegrityAudit().audit([t(10,0),t(12,1),t(12,2)])["groups"][("tabdeal","BTC_USDT")]
    assert report["sequence_gap_total"] == 1
    assert report["largest_sequence_gap"] == 1
    assert report["duplicate_sequence_count"] == 1

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
    assert [t.sequence for t in result]==[1,2]
