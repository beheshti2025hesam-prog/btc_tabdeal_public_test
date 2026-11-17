# Immutable Release Manifest v1

## Purpose

HES_RELEASE_MANIFEST_v1.json and its SHA-256 sidecar are required by the operational recovery gate. The manifest proves that the files installed under releases/<commit-sha> are byte-for-byte identical to the blobs in that exact Git commit.

The manifest is a deployment artifact, not application runtime data. It must be generated once for each release before the release directory is made read-only and before the current symlink is switched.

## Required deployment order

1. Resolve and record the full 40-character commit SHA.
2. Extract that exact commit into /opt/hes-trade-agent/releases/<commit-sha>.
3. Run the manifest builder from the Git checkout that contains the commit object:

   python3 scripts/ops/build_release_manifest_v1.py --repo-root /opt/hes-trade-agent --release-dir /opt/hes-trade-agent/releases/<commit-sha> --commit-sha <commit-sha>

4. Require status=PASS and record manifest_sha256 plus files_checked in the deployment record.
5. Verify the manifest pair exists and is readable. Only then make the release directory and its files read-only.
6. Atomically switch /opt/hes-trade-agent/current to the new release.
7. Keep the deployment lock held while switching the pointer. The operational recovery service deliberately waits until the pointer has been stable for 600 seconds before any bounded paper-worker recovery is eligible.
8. Run the operational healthcheck and require overall=OK before considering the deployment healthy.

## Integrity and fail-closed rules

- The builder enumerates the exact Git tree with NUL-delimited paths and hashes only tracked blobs. Runtime-generated __pycache__ files and other untracked artifacts are not silently included.
- Every tracked file must exist in the release and match the Git blob byte-for-byte before a manifest is written.
- Symlinks and Git submodules are rejected because the current release verifier expects regular files contained by the immutable release.
- Path traversal, duplicate paths, missing files, modified files, malformed Git tree entries, and invalid commit IDs fail closed.
- The JSON manifest is accompanied by HES_RELEASE_MANIFEST_v1.sha256, which hashes the exact manifest bytes.
- Existing manifest evidence is never overwritten. A complete existing pair is accepted only if its hashes verify and its commit/file identity matches the newly built candidate. A partial or conflicting pair requires operator investigation.
- The builder does not change permissions on the release directory. Run it while the deployment process still has write access; make the release immutable only after it passes.

## Tests

Run: pytest -q tests/ops/test_release_manifest_v1.py tests/ops/test_operational_recovery_v1.py

The tests cover exact Git-tree membership, ignored runtime cache files, idempotent generation, tamper/missing-file rejection, symlink rejection, and refusal to overwrite partial or conflicting evidence.

## Recovery boundary

A missing or invalid manifest is an operational integrity failure. The healthcheck must not bypass this gate or restart workers to work around it. Restore the missing deployment artifact only after proving that every tracked release file exactly matches the recorded Git commit; otherwise deploy a separately verified release.
