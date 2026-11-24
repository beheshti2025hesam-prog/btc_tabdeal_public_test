from __future__ import annotations
from datetime import datetime, timezone
import json
import pytest
from forward.trade_journal_view_v1 import read_decision_journal
from forward.sealed_jsonl_segments_v1 import iter_jsonl_entries, seal_hot_file, JsonlSegmentError

def row(i):
    return {"event_id":f"sealed-event-{i}","observed_at":datetime.now(timezone.utc).isoformat(),
      "symbol":"BTC_USDT","timeframe":"15m","decision":"NO_TRADE" if i%2==0 else "LONG",
      "evidence_source":"gateio_public_spot","execution_enabled":False,"orders_placed":False,
      "outcome":None,"closed_at":None}

def test_dashboard_projection_reads_sealed_segments_and_hot_tail(tmp_path):
    path=tmp_path/"trade_journal_v2.jsonl"
    rows=[row(i) for i in range(12)]
    path.write_bytes(b"".join((json.dumps(x,sort_keys=True)+"\n").encode() for x in rows[:8]))
    assert seal_hot_file(path) is not None
    with path.open("ab") as f:
        for x in rows[8:]: f.write((json.dumps(x,sort_keys=True)+"\n").encode())
    streamed=list(iter_jsonl_entries(path))
    assert [x["event_id"] for x,_ in streamed]==[x["event_id"] for x in rows]
    result=read_decision_journal(path,limit=20)
    assert result["status"]=="VERIFIED"
    assert result["count"]==12 and result["decision_count"]==12
    assert len(result["events"])==12
    assert result["execution_enabled"] is False and result["outcomes_inferred"] is False

def test_dashboard_projection_fails_closed_on_segment_corruption(tmp_path):
    path=tmp_path/"trade_journal_v2.jsonl"
    path.write_text(json.dumps(row(1))+"\n")
    assert seal_hot_file(path) is not None
    manifest=path.with_name(path.name+".segments")/"manifest.json"
    data=json.loads(manifest.read_text())
    data["segments"][0]["record_count"]+=1
    manifest.write_text(json.dumps(data))
    with pytest.raises((JsonlSegmentError,ValueError)):
        list(iter_jsonl_entries(path))