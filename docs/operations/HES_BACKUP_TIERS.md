# HES backup tiers — Dropbox capsule + full Restic secondary

## Storage math
The latest full Restic snapshot measured 3.434 GiB raw repository data and 2.844 GiB after Restic compression (1.21x). A 400 MiB cap cannot contain this full repository. Recompressing encrypted/already compressed objects is not a valid capacity strategy.

## Tier 1 — Dropbox recovery capsule
- Maximum 24 MiB per encrypted capsule; two remote generations are retained, for at most 48 MiB of HES capsule objects.
- Contains current core, dashboard and precision releases; verified rollback release trees; service/system configuration; operational health and release manifests; dependency inventories; docs/reports and compact project evidence.
- Excludes full Restic packs, bulk evidence, old candidates/worktrees, caches, virtualenv binaries and the recovery passphrase.
- Zstandard level 19 is applied before GPG AES-256; cap is enforced during streaming. Decrypt, zstd, tar listing and release coverage are verified before publication.
- Publish is immutable/versioned, quota-gated with 128 MiB reserve, and reads the new remote object back for checksum/decryption/compression/tar validation.
- Daily systemd cycle is scheduled for 04:00 UTC at low CPU/IO priority. It retains 7 local capsules and 2 remote capsules; remote rotation verifies both retained generations and deletes only older files matching the exact capsule filename pattern. After migration and only after the full secondary Restic restore gate passes, create /etc/hes-trade-agent/backup/enforce-dropbox-20pct. The scheduled publisher then enforces account-wide Dropbox used storage at or below 20% of the actual quota before upload and after rotation. Until that marker exists, the publisher still enforces the free-quota 128 MiB reserve but does not enforce the 20% used-storage target during the migration window.

## Tier 2 — full encrypted Restic
- Copy the complete local Restic snapshots to a separately authorized larger free-tier remote using Restic's native copy command. Initialize the destination with the source chunker parameters so identical data deduplicates across copied snapshots; apply the same scope-aware Restic retention to the remote.
- Verify source-to-destination snapshot metadata coverage, then run remote restic check. Native Restic copy re-encrypts data and can use a different pack layout, so byte-for-byte rclone directory equality is not the correct validation.
- Google Drive is a candidate only: a standard account offers up to 15 GB shared with Gmail and Photos; actual free quota must be checked after owner authorization. No credential or remote is configured by this change. Use the least-privilege drive.file scope for the dedicated rclone-created backup folder. Since rclone's shared Google client ID is being retired during 2026, the owner must create and use a personal OAuth client ID/secret; do not rely on the shared default.
- A separate daily 03:30 UTC Restic Drive timer/service is provided but must remain disabled until the owner authorizes the rclone remote and the actual free quota passes the 512 MiB reserve gate.
- Full isolated restore is mandatory before retiring any existing Dropbox object.

## Retention invariants
- Never delete the incomplete Dropbox Restic mirror or the 2026-11-16 capsule until the secondary full repository passes full read-data integrity and isolated restore.
- Keep a rollback capsule during migration. Do not touch unrelated Dropbox content.
- Local Restic retention remains scope-aware (7 daily, 4 weekly, 6 monthly, 2 yearly).
- Unknown, unclassified or un-restored files are KEEP.
- No automatic remote pruning. No deletion before verified replacement and restore.

## Verified measurements — 2026-11-20
- Local Restic repository: about 3.2 GiB on disk; 6 full-scope snapshots.
- Latest full snapshot: 9.089 GiB restore-size; 3.434 GiB raw; 2.844 GiB Restic-compressed; 1.21x.
- Dropbox Restic mirror: 72 objects / 981,413,452 bytes; 72 matched, 146 local-only, zero remote-only; incomplete subset.
- Dropbox quota: 2,147,483,648 total; 1,743,885,121 used; 403,598,527 free.
- Old compact archive: 398,216,865 bytes, 2026-11-16, predates latest dashboard release.
- Local Restic full read-data check passed 205/205 packs and 6/6 snapshots.
- The 400 MiB full-scope archive builder correctly rejected the new release set.
- No Dropbox objects were deleted or overwritten.


## First successful capsule build and isolated restore — 2026-11-20

- Built a fresh encrypted capsule from the live VPS after discovering six active/rollback release trees.
- Encrypted artifact: 15,833,570 bytes (about 15.1 MiB), SHA-256 4026e3654698b3a1991c7cf2a37ca1ff6ffd64e0ab13899b62248430f1b7f0b8.
- GPG decryption, Zstandard integrity, tar member coverage and isolated extraction all passed; the isolated restore verified all six release directories plus core/dashboard/precision symlinks and critical config/runtime paths.
- This is the first current capsule candidate; it has not yet been uploaded to Dropbox. No remote object was changed.
- The 24 MiB per-capsule cap leaves headroom for release growth; two remote versions are capped at 48 MiB total. Account-wide 20% enforcement is enabled only after the complete Restic secondary migration marker is created.


References: Google storage allowance https://support.google.com/googleone/answer/9004014 ; rclone Drive backend/scopes and client ID requirements https://rclone.org/drive/.
