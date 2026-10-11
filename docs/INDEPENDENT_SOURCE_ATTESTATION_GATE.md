# Independent Source Attestation Gate — Design and Acceptance Criteria

Status: DESIGN / NOT IMPLEMENTED
Date: 2026-10-11
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
