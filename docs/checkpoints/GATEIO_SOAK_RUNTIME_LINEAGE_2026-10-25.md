# Gate.io soak runtime lineage — 2026-10-25

## Disposition

**IN_PROGRESS / DIAGNOSTIC_ONLY / HOLD.** This document captures the exact runtime components observed during the active read-only Gate.io soak. It is not a 24-hour pass, not a clean-checkout claim, and not permission to merge, deploy, enable a collector, or trade.

## Runtime

- Project path: `/opt/hes-trade-agent`
- VPS branch: `feat/gateio-global-market-data-v1`
- VPS HEAD: `b2466bc118217dcc6446498effe38181589ed2db`
- Parent: `4956cf519c445edd004fdd4e763bdb3347a7ada9`
- The local HEAD was not resolvable as a GitHub ref when attempting to create a branch from that SHA; treat the full working tree as **not remotely pinned**.
- Working tree at orientation: 0 staged, 11 unstaged, 50 untracked paths, 345 deletions in the summary. No reset, clean, checkout, or deploy was performed.
- Soak service: `hes-global-market-data-gateio-soak.service`
- Soak process start: `2026-10-25T11:48:04Z`
- First v2 sample: `2026-10-25T11:48:05Z`
- Latest captured sample at audit time: `2026-10-25T16:24:33Z`, sample 277, elapsed 16,588 seconds; all 277 samples were `ok=true`.
- Required final conditions remain at least 86,400 seconds, at least 1,400 valid samples, no invalid samples, and a written `hes_gateio_soak_summary_v2` with `passed=true`. The run had not reached those conditions at capture time.

## Runtime code hashes

| Component | Runtime SHA-256 | Repository evidence |
|---|---|---|
| Active soak runner `scripts/soak_gateio_feed_24h_v2.py` | `435404c3694455015ef9d26c23544e44f5809dbf2dceefea3401704f8d0328a8` | Exact file committed on this branch; verified by downloading the immutable commit path and comparing SHA-256 |
| Active reader `forward/global_market_data_reader_v1.py` | `ef39445a1356de71a25d174ce30dd88dffb0d6377ac623c186203a3e5d120e41` | Exact runtime bytes preserved at `evidence/runtime_snapshots/2026-10-25/global_market_data_reader_v1.py`; verified SHA-256 |
| Feed implementation `forward/global_market_data_gateio_v1.py` | `128f4af844d6ad477568bb82706ee5d00f3701004cc81479f71ff04cad87c06f` | Matches public branch `feat/gateio-global-market-data-v1` |
| Service wrapper `scripts/run_global_market_data_gateio_service.py` | `280992fe64c1a2d4d97ded6992a5f0ab9b275e7ce440872891ebf4a45bf76919` | Matches public branch `feat/gateio-global-market-data-v1` |
| Active soak unit `/etc/systemd/system/hes-global-market-data-gateio-soak.service` | `724bd70c95346e1b97630faa6b82ed4135df62667bd6bd8c892b6941883837b6` | Host-side read-only hash captured |

## Integrity limits

- The active soak runner was untracked when it started. Its exact bytes are now preserved and hash-verified in the repository candidate branch.
- The active reader bytes differ from the current public branch reader; the exact runtime reader has therefore been preserved separately instead of falsely claiming it came from the public branch's reader path.
- Because the VPS HEAD and working tree were not cleanly pinned as a single remote commit, this run remains diagnostic until the final evidence review accepts the per-file lineage and all sample records.
- Gate.io feed services were observed active; the legacy Tabdeal collector service was observed failed/disabled and was not started or changed.
- Execution remained disabled and `orders_placed=false`. No live trading or service mutation was performed for this capture.
