"""Fail-closed recovery probe for the original 1,049 OOS population."""
import hashlib, json
from pathlib import Path
from core.backtest.real_data import RealDataBacktest
from core.backtest.oos_protocol import REAL_BTC_USDT_OOS_V1

RAW_SHA256 = "2c2d075f80ade4eba402809a106ab265eddba081"
EXPECTED = {"fold_count": 8, "evaluated": 1049, "wins": 528, "losses": 479,
            "gross_total_return": 0.027839866468923342}

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    path = Path("data/trades.csv")
    digest = sha256_file(path)
    runner = RealDataBacktest(str(path))
    wf = runner.run_walk_forward(
        train_size=REAL_BTC_USDT_OOS_V1.train_size,
        test_size=REAL_BTC_USDT_OOS_V1.test_size,
        step_size=REAL_BTC_USDT_OOS_V1.step_size,
        embargo_size=REAL_BTC_USDT_OOS_V1.embargo_size,
        max_folds=REAL_BTC_USDT_OOS_V1.expected_fold_count,
    )
    observed = {
        "raw_sha256": digest, "fold_count": len(wf.folds),
        "evaluated": wf.evaluated, "wins": wf.wins, "losses": wf.losses,
        "gross_total_return": wf.total_return,
        "fold_evaluated": [f.result.evaluated for f in wf.folds],
    }
    print(json.dumps(observed, indent=2, sort_keys=True))
    if digest != RAW_SHA256:
        raise SystemExit("FAIL-CLOSED: raw SHA mismatch")
    for key in ("fold_count", "wins", "losses", "gross_total_return"):
        if observed[key] != EXPECTED[key]:
            raise SystemExit(f"FAIL-CLOSED: {key}: {observed[key]!r} != {EXPECTED[key]!r}")
    if observed["evaluated"] != EXPECTED["evaluated"]:
        raise SystemExit(
            "FAIL-CLOSED: exact 1,049 population was not reproduced; "
            f"replay produced {observed['evaluated']}. No snapshot emitted."
        )

if __name__ == "__main__":
    main()
