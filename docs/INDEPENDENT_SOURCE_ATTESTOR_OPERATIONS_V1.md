# Independent Source Attestor Operations v1 (Design Gate)

Status: DESIGN ONLY — not evidence of a real retrieval, signature, or source identity.

## Purpose

The detached attestation verifier checks that a configured Ed25519 public key signed a statement whose SHA-256 matches the exact snapshot bytes. It does **not** prove by itself that the signer actually retrieved those bytes from the claimed source. This document defines the external controls required before a production attestation may be trusted.

## Separation of duties

1. The attestor runs in an independently controlled environment, not in a pull-request workflow and not from files supplied by the PR.
2. The signing private key is never stored in this repository, the snapshot directory, a runner image, workflow logs, or a developer shell history.
3. The verifier's public key is provisioned through protected runtime configuration outside PR-writable files. A registry entry, lock file, snapshot, or attestation cannot select or replace the trust root.
4. A key owner/reviewer approves key creation, rotation, revocation, and the mapping from `signer_key_id` to the public key.

## Required retrieval procedure

1. Fetch the exact official source URL over HTTPS using a documented retrieval tool.
2. Record each HTTP redirect hop in order, with the URL and integer response status. The first hop URL must equal `requested_url`; the last must equal `final_url`.
3. Preserve the exact response bytes used as the snapshot. Do not reformat, normalize, re-encode, or manually edit the bytes after retrieval.
4. Calculate SHA-256 from those exact bytes.
5. Populate the `hes-source-attestation-v1` statement with the digest, requested/final URLs, complete redirect chain, UTC retrieval time, retrieval tool/version, exact source context, and signer key ID.
6. Sign the canonical JSON payload (UTF-8, keys sorted, compact separators, non-ASCII preserved; omit only the `signature` field) with the externally governed Ed25519 private key.
7. Publish the snapshot and detached attestation as a matched pair, with their hashes recorded in the review record. Never issue a signature for a snapshot that was not retrieved by this process.

## Review gates before any positive sequence claim

- Independently reproduce the retrieval and compare the raw snapshot digest.
- Confirm the source is an official, scope-appropriate primary source and inspect the exact text that supports each capability claim.
- Confirm signer identity and key status through the independent key-governance record.
- Review the registry and its lock on the exact commit; check that each evidence record points to the verified snapshot and attestation.
- Run adversarial tests, including missing trust root, wrong key, signature tampering, snapshot-byte tampering, redirect-chain mismatch, unsafe paths, and coordinated registry+lock replacement.
- Require independent reviewer approval. A green CI run alone is not source-identity approval.

## Fail-closed rules

- Missing snapshot, attestation, trust root, signer authorization, or any digest/signature/context/URL mismatch means BLOCK.
- No fallback to unsigned metadata, manually copied excerpts, or a repository-local key.
- A successful attestation proves only that the configured key signed the statement about the snapshot. Trust in the retrieval process depends on the external controls above.
- Until the source contract explicitly establishes sequence semantics, `trade.sequence` remains `unknown`; do not infer ordering, uniqueness, contiguity, or gap detection from numeric-looking values.
- This design document is not itself source evidence and does not authorize live observation, evidence unlock, or trading.
