# HES Source Identity Reconciliation — Progress Checkpoint
Date: 2026-10-13
Status: HOLD — SOURCE IDENTITY NOT VERIFIED

## Guardrails
- Do not change winner selection, thresholds, tuning, source records, or historical artifacts.
- Do not delete, normalize away, or overwrite discrepancies.
- No feature extraction, Effective Evidence calculations, promotion, or live execution until record identity is independently proven and a new immutable reconciliation artifact is hash-locked.

## GitHub artifacts located
- Reconciliation artifact: evidence/source_identity_reconciliation_v1.json
  - GitHub blob SHA reported by Contents API: d21a37bb239249ebe16678a1e21d698e0db68472
  - Its declared scope is record identity only; it lists 14 prior Survivor and 28 current Winner records and reports 0 exact record-key matches.
- Prior lock: evidence/source_identity_reconciliation_v1.lock.json
  - Declared artifact SHA-256: db2c16104034d81d6d0e3b5daee72cd3df97f207e005040aee09c2c8d3b6fcfd
  - Declared artifact size: 17,937 bytes; 42 records; 14 prior; 28 current.
  - The artifact file's SHA-256 still needs independent recomputation from exact bytes before accepting this lock.
- Current raw protocol snapshot artifact:
  - Workflow run: 37125436806
  - Artifact ID: 11275181041
  - Artifact name: independent-raw-protocol-reconciliation-v1
  - ZIP size: 10,833 bytes
  - GitHub artifact Digest and locally recomputed ZIP SHA-256 both equal:
    95a49f8b8ab61038d8f1ba3c4f739126c5a5959b5f9ca329eca94b44c4b379af
  - ZIP members: independent_raw_snapshot_lock.json (739 bytes), protocol_reconciliation_full_population_audit.json (42,177 bytes), protocol_reconciliation_winners.csv (5,718 bytes).
  - The internal raw snapshot lock declares data/trades.csv SHA-256 c6c20f30fc6cbf6934c81e7b5e0495f952b7bab5fe2978baca6fdd78c68b90e6, 10,501,596 bytes, 139,250 rows, source commit b9ebecf061dfe9a084797d77b48a2c7846d269e3 and Git blob 58d21825e052dbaa42e7eb0695455c19997bff43. The raw CSV bytes themselves were not included in this ZIP, so those raw-file claims are not independently rehashed yet.
- Prior analysis artifact:
  - Workflow run: 37311909412
  - Artifact ID: 11346536218
  - ZIP size: 3,412 bytes
  - ZIP SHA-256 locally recomputed and equal to GitHub Digest:
    7cada3e15a86832595162972a9dbe8368d764b67bff8f1b6a0fc0c8a58eabca5
  - Contains cross_lineage_effective_evidence_v1.json. This is a prior analysis artifact, not the missing original raw-source proof for the 14 records.
- Prior raw-source reference found in GitHub:
  - Commit b8c4fe4fa054dbfa4fca17d2f307d269c16335e1
  - data/trades.csv Git blob 1a44d52a0588deb765bbbea04bfb5783dcb1050b; GitHub metadata size 9,592,808 bytes.
- Protocol contract reference:
  - Commit e5f85f06b19b8427f761b95ab56ad15ccd7053c0
  - Blob SHA a84dafbc09c72ac37ebbbb0706b43d23f7681e12.
- Existing archive lineage artifacts were located:
  - archive/vps_github_archive_identity_reconciliation_v1.json and .lock.json
  - archive/vps_github_current_tail_reconciliation_v1.json and .lock.json
  - archive/run196_reconciliation_closure.json
  - archive/run_196_final_checkpoint_lock.json
  - archive/run196_n_plus_1_preflight_audit_v2.json
  - archive/run196_n_plus_1_startup_evidence.json
  These are useful lineage/context, but do not substitute for direct record-to-raw-source validation for the 42-record reconciliation.

## Current findings
- Both downloaded ZIP archives passed independent SHA-256 comparison against the GitHub artifact Digests.
- The 42-row identity artifact and its lock are present in GitHub, but the lock's declared SHA-256 has not yet been independently recomputed from the exact artifact bytes.
- Current and prior source CSV blob identities are known from GitHub metadata, but their complete raw bytes were not available in the downloaded ZIPs. Direct raw-row matching is still pending.
- The reconciliation artifact reports 0 exact matches between the 14 prior Survivor and 28 current Winner keys. Treat this as a recorded claim, not an independently confirmed conclusion, until raw-source matching is complete.
- Recent Effective Evidence Audit workflow runs 38350552232 and 38350588500 were observed as completed with conclusion "skipped"; do not interpret these as successful evidence-gate passes.
- Existing Run #196 closure says the legacy collector handoff and N/N+1 boundary were closed in that earlier scope. Keep it separate from this 42-record source-identity gate.

## Next steps — execute in order
1. Re-fetch exact reconciliation JSON and lock at a fixed commit; independently calculate UTF-8 byte count and SHA-256 of the JSON bytes and compare to lock fields. Resolve any mismatch as a recorded discrepancy; do not update the old lock.
2. Retrieve the raw source CSV bytes at the exact prior commit b8c4fe4fa054dbfa4fca17d2f307d269c16335e1 and current commit b9ebecf061dfe9a084797d77b48a2c7846d269e3, or obtain original source archives with verifiable provenance.
3. Independently hash raw files and compare byte lengths, Git blob SHA-1 (using Git's canonical blob formula), and recorded SHA-256 where available.
4. Match all 14 prior and 28 current records against their source rows using the frozen key:
   timestamp, sequence_first, sequence_last, entry_price, exit_price, gross_return, direction.
5. Record missing, extra, duplicate, conflicting, timestamp, and sequence-range findings without changing source evidence.
6. Reconcile archive lineage and writer attribution/single-writer proof for any relevant intervals.
7. Only if every gate passes, create a new immutable reconciliation artifact and its new hash lock. Never rewrite the historical artifact/lock to make them agree.

## Resume phrase
“ادامه از Master Checkpoint 2026-10-13 — HOLD / SOURCE IDENTITY NOT VERIFIED؛ اول هش واقعی فایل تطبیق و قفل را مستقل محاسبه کن، سپس raw CSVهای دقیق دو Commit را بازیابی و ۴۲ رکورد را تطبیق بده. هیچ استخراج ویژگی یا محاسبه Effective Evidence انجام نده.”
