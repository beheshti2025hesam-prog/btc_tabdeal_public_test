    # observation universe. The historical evidence contract covers the
    # deterministic first 4,062 chronological observations; the 8 folds use
    # the first 4,000 of that frozen universe and leave the final 62 as
    # post-protocol tail. Do not discard or rewrite the raw tail.
    if len(all_rows) < EXPECTED_FROZEN_OBSERVATIONS:
        raise AssertionError(
            f"chronological observation count below frozen contract: {len(all_rows)} "
            f"< {EXPECTED_FROZEN_OBSERVATIONS}"
        )
    frozen_rows = all_rows[:EXPECTED_FROZEN_OBSERVATIONS]
    # The frozen 8-fold OOS protocol consumes 4,000 observations
    # (800 train + 8*400 test). Keep both boundaries explicit:
    # OOS protocol end and the full 4,062-observation frozen-universe end.
    expected_oos_last = "2026-09-26T10:04:00+00:00"
    oos_last_index = 8 * 400 - 1
    if frozen_rows[oos_last_index][0].end.isoformat() != expected_oos_last:
        raise AssertionError(
            "frozen OOS boundary mismatch: "
            f"{frozen_rows[oos_last_index][0].end.isoformat()} != {expected_oos_last}"
        )
    expected_frozen_last = "2026-09-27T17:30:00+00:00"
    if frozen_rows[-1][0].end.isoformat() != expected_frozen_last:
        raise AssertionError(
            "frozen observation boundary mismatch: "
            f"{frozen_rows[-1][0].end.isoformat()} != {expected_frozen_last}"
        )

    selected=[]
    start=0
    fold=0
    fold_counts=[]
    while fold < EXPECTED_FOLDS:
        train_end=start+800; test_start=train_end; test_end=test_start+400
        if test_end > len(all_rows): break
        fold_eval=0
        for idx in range(test_start,test_end):