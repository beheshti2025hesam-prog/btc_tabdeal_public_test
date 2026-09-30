import importlib.util
from pathlib import Path


def load_script():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "independence_adjusted_evidence.py"
    spec = importlib.util.spec_from_file_location("independence_adjusted_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_independence_evidence_helpers():
    module = load_script()

    assert module.kish_ess([2, 3, 2, 7]) == 196 / 66
    assert module.kish_ess([7]) == 1.0
    assert module.kish_ess([]) == 0.0

    assert module.smd([1.0, 2.0], [0.0, 1.0]) != 0.0
    assert module.smd([], [1.0]) is None

    # The independence layer must remain evidence-only.
    assert module.EXPECTED_RUN_ID == 36489452534
    assert module.EXPECTED_BLOB == "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
