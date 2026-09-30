import json
import subprocess
import sys
from pathlib import Path

def test_independence_evidence_script():
    root = Path(__file__).resolve().parents[2]
    subprocess.run(
        [sys.executable, str(root / "scripts" / "independence_adjusted_evidence.py")],
        cwd=root,
        check=True,
    )
    p = root / "independence_adjusted_evidence.json"
    x = json.loads(p.read_text())
    assert x["population"]["nominal_winners"] == 14
    assert x["population"]["nominal_controls"] == 1035
    assert x["independence_unit"]["winner_supported_fold_count"] == 4
    assert x["population"]["winner_fold_sizes"] == [2, 3, 2, 7]
    assert x["interpretation"]["signal_created"] is False
