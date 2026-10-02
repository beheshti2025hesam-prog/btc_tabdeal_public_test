import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "evidence/candidate_c_fresh_snapshot_1m_gap_forensics_v1.json"

def test_candidate_c_snapshot_gap_forensics():
    a = json.loads(ART.read_text())
    assert a["status"] == "OOS_BLOCKED_GAP_FORENSICS"
    assert a["active_blob"] == "eef65102d4671a43f11f9dc311e0617aa220eb64"
    assert a["bars_1m"] == 4977
    assert a["gaps_found"] == 8
    assert a["safety"]["oos_started"] is False
    assert a["safety"]["live_execution"] is False
    assert a["safety"]["promotion"] is False
    first = a["first_failure_gap"]
    assert first["bar_index_before"] == 265
    assert first["missing_minutes"] == 270
    assert first["prev_minute_utc"] == "2026-09-27T03:45:00.000Z"
    assert first["next_minute_utc"] == "2026-09-27T08:16:00.000Z"
    # The previously locked 1049 Fold-7 gap must remain identifiable and untouched.
    locked = next(
        g for g in a["gaps"]
        if g["prev_last_event_utc"] == "2026-09-27T12:03:19.239Z"
        and g["next_first_event_utc"] == "2026-09-27T17:16:54.102Z"
    )
    assert locked["missing_minutes"] == 312
    assert locked["elapsed_seconds"] == 18814.862999916077
    assert locked["prev_last_sequence"] == 38354073619
    assert locked["next_first_sequence"] == 38413063944
