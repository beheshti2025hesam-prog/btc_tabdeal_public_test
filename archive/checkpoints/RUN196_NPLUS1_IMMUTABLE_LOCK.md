# Run #196 — N+1 Immutable Checkpoint Lock

Status: LOCKED

## Locked checkpoint
- Checkpoint commit: 37f8c32b6398688575a32912f590bc9b10058363
- Parent checkpoint: a03f0ed1ca15c584c910f392abdf370dde80510f
- Previous Closure/Handoff Base: 6dec117f95c677cfa1216c6b4406dd3da9982ccd
- Commit subject: Checkpoint Tabdeal BTC_USDT trades
- Commit delta: data/trades.csv only; 532 additions; 0 deletions

## Restart-boundary proof
- Collector restart was performed on the VPS after checkpoint a03f0ed1.
- Collector was active again with a new MainPID.
- Restart did not alter or delete the persisted tail at a03f0ed1.
- Post-restart collection continued from the persisted boundary.
- Subsequent live audit observed no sequence duplicates and no sequence regressions.

## Single-writer proof
- data/.collector.lock remained present.
- The active collector process held the lock.
- The active collector process was the only observed writer of data/trades.csv.

## Reconciliation result
- GitHub checkpoint chain is linear:
  6dec117f -> 542c4f2 -> e95ef93 -> 8acdc1f -> a03f0ed1 -> 37f8c32
- No deletion was observed in the checkpoint deltas.
- No reset, force-rewrite, or overwrite was used to establish this checkpoint.
- The live CSV may continue to grow after this lock; that mutable suffix is intentionally NOT part of this immutable lock.

## Gate
N+1 persistence: PASS
Restart boundary: PASS
Gap classification: PASS
Duplicate classification: PASS
Single-writer continuity: PASS
Closure preservation: PASS
Immutable N+1 checkpoint: LOCKED

This artifact locks the checkpoint identity and reconciliation evidence. It does not freeze ongoing live collection.
