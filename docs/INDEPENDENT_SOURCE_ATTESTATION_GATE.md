# Independent Source Attestation Gate — Design and Acceptance Criteria

Status: PARTIAL IMPLEMENTATION / PRODUCTION TRUST ROOT NOT VERIFIED
Date: 2026-10-11

## Implementation checkpoint (2026-10-11)

Implemented in the current code path: detached Ed25519 attestation verification; strict trust-key ID matching; raw snapshot SHA-256 comparison; requested/final URL and source-context binding; fail-closed runner gate before session creation and WebSocket transport construction; registry/lock digest validation; adversarial tests for signature tampering, wrong keys, missing/mismatched key identity, coordinated registry+lock replacement, and pre-network blocking.

Not established by these tests: that the production trust key is independently governed outside PR control; that the production registry contains an attestation produced by an independently operated retriever; that the recorded redirect chain was observed from a real HTTP exchange; or that Tabdeal defines `trade.sequence` semantics. Synthetic test keys and synthetic source snapshots are test fixtures only.

Current production decision: `trade.sequence` remains `unknown`; gap detection remains disabled; runner remains blocked before socket/session creation while the checked-in production evidence lacks a valid independently trusted attestation. A green CI run is test evidence, not source-authenticity evidence.
Scope: HES Trade Agent exchange-sequence capability registry and controlled forward-observation runner.

## Safety invariant

Until every acceptance criterion below is met, `trade.sequence` remains `unknown`, sequence-gap detection remains disabled, and the runner must fail closed before opening a WebSocket, writing a session, or starting forward observation. This document does not authorize evidence unlock, live observation, order placement, or trading.

## Threat model

The current registry verifier can validate a local snapshot digest and declared URL/host fields. These checks do not independently prove that the bytes were retrieved from the declared URL or that a declared final URL reflects a real redirect chain. If the registry and its lock are both writable in the same repository change, matching hashes are not an independent trust anchor.

A source attestation must therefore be verified using trust material that cannot be replaced by the same pull request that changes the registry and lock.

## Required attestation record

The attestation must bind, at minimum:

- Exact SHA-256 of the raw retrieved response bytes (hash bytes, not a normalized/re-serialized document).
- Requested URL and final URL.
- Ordered redirect chain, including HTTP status for each redirect and the final response.
- Retrieval timestamp in UTC.
- Retrieval tool name and version, plus relevant request metadata needed to reproduce the retrieval.
- Source identity and the exact endpoint/channel/product context to which any claimed sequence semantics apply.
- Attestation schema/version and signer key identity.
- Signature over a canonical representation of all fields above.

Do not include credentials, API secrets, cookies, authorization headers, or other sensitive request values in the public artifact.

## Trust boundary

- The signature verification key or trust policy must be anchored outside the registry and lock files that the PR can modify.
- A checked-in public key is not sufficient if an unreviewed PR can replace both that key and the data it authenticates. The trust root must be protected by independently governed repository policy, a pinned external trust configuration, or an equivalent controlled identity/signing mechanism.
- A URL allow-list is a policy check, not proof of retrieval.
- A hash is an integrity check, not source authenticity.
- A successful CI run proves only that the tested checks passed for that commit; it does not replace independent source provenance or human review.

## Required fail-closed behavior

1. Missing, malformed, unsigned, invalidly signed, expired (if expiry is defined), or unknown-signer attestation => BLOCK.
2. Snapshot digest mismatch => BLOCK.
3. Requested URL, final URL, redirect chain, retrieval metadata, source context, or attested digest mismatch => BLOCK.
4. Registry and lock mismatch => BLOCK.
5. Coordinated registry + lock replacement without a valid attestation from the external trust root => BLOCK.
6. Unknown or unsupported sequence semantics => BLOCK before socket creation and session writes.
7. Test fixtures and synthetic snapshots may test rejection/validation logic, but must never be promoted as production provenance.

## Adversarial tests required

- Forged snapshot whose content is invented but whose registry digest and lock are updated together.
- Fabricated `final_url` with no matching attested redirect chain.
- Redirect chain omits a hop, reorders hops, or changes a status code.
- Snapshot bytes change by one byte after attestation.
- Attestation signature is invalid, signed by an unknown key, or uses an unsupported schema.
- Coordinated replacement of both registry and lock in one commit.
- Registry points to a different product, market, endpoint, channel, or sequence field than the attestation.
- Synthetic test snapshot accidentally enters the production verification path.
- Default checked-in conservative registry: assert runner returns BLOCKED before socket factory invocation and before session/event writes.
- Verify failure is deterministic and does not fall through to an unverified legacy path.

## CI and review acceptance

- Run all relevant unit, integration, adversarial, and regression tests on the exact final commit SHA.
- Record workflow run URLs, conclusion, commit SHA, and test counts from actual CI results.
- Confirm there is no live socket or order placement in CI tests.
- Require a human independent review from an authorized reviewer other than the change author; an issue/PR comment or automated assistant audit is not that review.
- Keep the PR Draft and unmerged until every criterion is satisfied.

## Explicit non-goals

- No change to historical evidence, winner selection, thresholds, or record deletion.
- No enabling sequence-gap detection merely because an attestation exists; the attested source must actually document the exact semantics for the relevant product/channel.
- No secrets in source, registry, logs, or public artifacts.
- No live observation, evidence unlock, or trading as part of this gate.

## Completion checklist

- [ ] Independent trust root is defined and protected outside PR-writable files.
- [ ] Retrieval/attestation producer and verifier are implemented and documented.
- [ ] All adversarial tests above pass.
- [ ] Production-path fail-closed tests pass.
- [ ] Exact-head CI passes.
- [ ] Independent human review is recorded.
- [ ] Sequence semantics are still marked unknown unless authoritative, context-matched evidence supports a narrower claim.

## Producer utility checkpoint (2026-10-12)

A first producer utility now exists at `scripts/independent_source_attestor_v1.py`. It retrieves raw HTTPS response bytes, records observed redirect hops/statuses, enforces an exact-host allow-list for the initial URL and redirects, hashes the raw bytes, and emits a detached Ed25519 signature. The private key and signer key ID are required from runtime environment configuration; they are not checked into source. A response-size cap and credential-free HTTPS URL checks are enforced.

The producer has focused tests for exact-host URL policy, missing signing-key fail-closed behavior, canonical payload stability, and attestation/verifier schema compatibility. These tests use synthetic fixtures only and are not production source evidence. The sequence-gate CI workflow now includes the producer test module.

Operational boundary: do not run this producer in ordinary PR CI with a signing secret. Run it only in a separately governed trusted environment after the trust root and key custody are independently established. No production snapshot or attestation is created by this code change itself.

- [ ] Independently governed signing key provisioned and custody documented.
- [ ] Producer run from trusted environment against an authoritative source.
- [ ] Raw snapshot and signed attestation reviewed and pinned in registry.
- [ ] Exact-head CI passes including producer tests.
