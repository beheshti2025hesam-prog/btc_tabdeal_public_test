from scripts.ops.hes_restic_offsite_capacity_gate_v1 import (
    DEFAULT_RESERVE_BYTES, evaluate_capacity,
)

def test_blocks_repository_larger_than_free_quota_plus_reserve():
    q = {"total": 2_147_483_648, "used": 1_366_621_708, "free": 780_861_940}
    p = evaluate_capacity(818_060_463, q)
    assert p["status"] == "BLOCKED_INSUFFICIENT_FREE_QUOTA"
    assert p["shortfall_bytes"] == 104_307_387
    assert p["transfer_authorized"] is False
    assert p["automatic_action"] == "NONE"

def test_passes_only_when_repository_and_reserve_fit():
    q = {"total": 2_147_483_648, "used": 1_000_000_000, "free": 1_147_483_648}
    p = evaluate_capacity(800_000_000, q, 64_000_000)
    assert p["status"] == "PASS_CAPACITY"
    assert p["shortfall_bytes"] == 0
    assert p["transfer_authorized"] is False

def test_exact_boundary_passes():
    repo = 100_000_000
    reserve = DEFAULT_RESERVE_BYTES
    q = {"total": 500_000_000, "used": 500_000_000-repo-reserve,
         "free": repo+reserve}
    assert evaluate_capacity(repo, q, reserve)["status"] == "PASS_CAPACITY"

def test_inconsistent_or_invalid_quota_fails_closed():
    assert evaluate_capacity(100, {"total": 1000, "used": 100, "free": 899})["status"] == "BLOCKED_INVALID_OR_INCONSISTENT_CAPACITY"
    assert evaluate_capacity(0, {"total": 1000, "used": 100, "free": 900})["transfer_authorized"] is False
    assert evaluate_capacity(100, {"total": 1000, "used": 100, "free": 900}, -1)["status"] == "BLOCKED_INVALID_OR_INCONSISTENT_CAPACITY"
