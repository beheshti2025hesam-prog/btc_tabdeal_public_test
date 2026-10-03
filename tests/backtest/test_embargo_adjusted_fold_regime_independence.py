import importlib.util
from pathlib import Path


def load_script():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "embargo_adjusted_fold_regime_independence.py"
    spec = importlib.util.spec_from_file_location("embargo_adjusted_fold_regime_independence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_is_locked_to_minimum_embargo():
    module = load_script()
    assert module.TRAIN == 800
    assert module.TEST == 400
    assert module.STEP == 400
    assert module.FOLDS == 8
    assert module.EMBARGO == 1
    assert module.OUTCOME_DELTA_SECONDS == 60
    assert module.THRESHOLD == 0.0014


def test_lineage_is_immutable():
    module = load_script()
    assert module.EXPECTED_BLOB == "1a44d52a0588deb765bbbea04bfb5783dcb1050b"
    assert module.EXPECTED_SOURCE_COMMIT == "b8c4fe4fa054dbfa4fca17d2f307d269c16335e1"
    assert module.EXPECTED_RUN_ID == 36489452534


def test_kish_ess():
    module = load_script()
    assert module.kish_ess([2, 3, 2, 7]) == 196 / 66
    assert module.kish_ess([7]) == 1.0
    assert module.kish_ess([]) == 0.0
