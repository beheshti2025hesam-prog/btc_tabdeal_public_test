import importlib.util
from pathlib import Path


def load_script():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "loo_fold_regime_independence_evidence.py"
    spec = importlib.util.spec_from_file_location("loo_fold_regime_independence_evidence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_kish_ess_and_sign_summary_are_deterministic():
    module = load_script()
    assert module.kish_ess([2, 3, 2, 7]) == 196 / 66
    summary = module.sign_summary([1.0, 2.0, -1.0, 0.0])
    assert summary["n"] == 4
    assert summary["positive"] == 2
    assert summary["negative"] == 1
    assert summary["zero"] == 1
    assert summary["sign_consistency"] == 0.5


def test_frozen_lineage_and_claim_boundary_are_constants():
    module = load_script()
    assert module.EXPECTED_BLOB == "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
    assert module.EXPECTED_SOURCE_COMMIT == "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
    assert module.EXPECTED_RUN_ID == 36489452534
    assert module.EXPECTED_FOLDS == 8
    assert module.EXPECTED_WINNERS == 14
    assert module.EXPECTED_CONTROLS == 1035
