# HES backup tiers — Dropbox capsule + full Restic secondary

## Storage math
The latest full Restic snapshot measured 3.434 GiB raw repository data and 2.844 GiB after Restic compression (1.21x). A 400 MiB cap cannot contain this full repository. Recompressing encrypted/already compressed objects is not a valid capacity strategy.

## Tier 1 — Dropbox recovery capsule
- Maximum 24 MiB per encrypted capsule; two remote generations are retained, for at most 48 MiB of HES capsule objects.
- Contains current core, dashboard and precision releases; verified rollback release trees; service/system configuration; operational health and release manifests; dependency inventories; docs/reports and compact project evidence.
- Excludes full Restic packs, bulk evidence, old candidates/worktrees, caches, virtualenv binaries and the recovery passphrase.
- Zstandard level 19 is applied before GPG AES-256; cap is enforced during streaming. Decrypt, zstd, tar listing and release coverage are verified before publication.
- Publish is immutable/versioned, quota-gated with 128 MiB reserve, and reads the new remote object back for checksum/decryption/compression/tar validation.
- Daily systemd cycle is scheduled for 04:00 UTC at low CPU/IO priority. It retains 7 local capsules and 2 remote capsules; remote rotation verifies both retained generations and deletes only older files matching the exact capsule filename pattern. After migration, the scheduled publisher enforces account-wide Dropbox used storage at or below 20% of the actual quota before upload and after rotation.

## Tier 2 — full encrypted Restic
- Mirror the complete local Restic repository to a separately authorized larger free-tier remote using append-only rclone copy.
- Verify exact content with rclone check and the repository itself with remote restic check.
- Google Drive is a candidate only: a standard account offers up to 15 GB shared with Gmail and Photos; actual free quota must be checked after owner authorization. No credential or remote is configured by this change.
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
