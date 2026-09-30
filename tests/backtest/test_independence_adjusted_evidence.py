import json
from pathlib import Path

def test_independence_evidence_schema():
    p = Path("independence_adjusted_evidence.json")
    assert p.exists()
    x = json.loads(p.read_text())
    assert x["population"]["nominal_winners"] == 14
    assert x["population"]["nominal_controls"] == 1035
    assert x["independence_unit"]["winner_supported_fold_count"] == 4
    assert x["population"]["winner_fold_sizes"] == [2, 3, 2, 7]
    assert x["interpretation"]["signal_created"] is False
