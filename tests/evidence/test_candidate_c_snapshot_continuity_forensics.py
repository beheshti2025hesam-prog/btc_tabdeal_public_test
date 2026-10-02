import json
from pathlib import Path

P = Path("evidence/candidate_c_snapshot_continuity_forensics_20261002.json")

def test_snapshot_continuity_forensics_is_fail_closed():
    d = json.loads(P.read_text())
    assert d["status"] == "RAW_SNAPSHOT_CONTINUITY_GAP_CONFIRMED_OOS_BLOCKED"
    assert d["bars_1m"] == 4977
    assert d["raw_rows"] == 135753
    assert d["gap_count"] == 8
    assert d["total_missing_full_minutes"] == 1949
    assert d["first_ci_failure"]["transition"] == "265->266"
    assert d["first_ci_failure"]["missing_full_minutes"] == 270
    assert d["first_ci_failure"]["location"] == "Fold 1 train"
    assert d["interpretation"]["evaluator_failure_is_real"] is True
    assert d["interpretation"]["exit_resolver_bug"] is False
    assert d["interpretation"]["synthetic_fill_allowed"] is False
    assert d["interpretation"]["interpolation_allowed"] is False
    assert d["interpretation"]["policy_change_allowed"] is False
    assert d["interpretation"]["oos_started"] is False
    assert d["safety"]["locked_1049_unchanged"] is True
