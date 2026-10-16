# HES Trade Agent — Master Checkpoint: Attestation Verifier Convergence
Date: 2026-10-13
Checkpoint: `ATTESTATION_VERIFIER_CONVERGENCE`
Disposition: `HOLD — PARALLEL VERIFIER IMPLEMENTATIONS NOT RECONCILED`

## Operating rule
- Memory = project map and plan.
- GitHub = technical source of truth.
- Chat = conversation log.
- Continue forward; do not repeat the 42-record reconciliation.
- Do not claim tests were newly rerun when this checkpoint only inspects existing GitHub Actions runs.

## Surgery performed: read-only GitHub audit
Inspected current PR metadata, exact head SHAs, existing workflow runs/jobs, and code/test diffs for source-attestation work. No code, data, lock, service, or trading state was changed.

### Confirmed existing CI runs (not rerun in this session)
- PR #262 verifier scaffold, exact head `ff4de94f8eee775655ab82f851714b37427844ee`: workflow run `38246066836`, “Independent Source Attestation v1”, job `attestation-verifier-tests` completed successfully.
- PR #259 freshness follow-up, exact head `c7c4e783b27bf3f728a0b64478d9359c738643fc`: workflow run `38214170993`, “Sequence Capability Registry v1”, job `registry-tests` completed successfully.
- PR #258 producer branch head `58229ab4607d928ac3bec4e43ed71455db368cf1`: workflow run `38211909779`, job `registry-tests` completed successfully.
- PR #252 registry head `6b63c71de2b08ccbbe9cc9c0691e45286a54d997`: workflow run `38119696244`, job `registry-tests` completed successfully.
- PR #253 raw-ingress journal head `bc97068ad4b18f973f1a651292c2d09c8030d712`: workflow run `38129655432`, job `raw-ingress-journal` completed successfully.
These results apply only to the exact commits and test jobs listed; they do not establish source authenticity, Tabdeal sequence semantics, full market-feed delivery, or production readiness.

## Critical finding: parallel verifier interfaces are not yet reconciled
- PR #262 is based on `feat/sequence-capability-registry-v1` and its verifier accepts a detached envelope with `payload_b64`, `signature_b64`, and a separate artifact SHA; it binds a single `expected_commit` and validates HTTPS URLs.
- PR #259 is based on `impl/detached-source-attestation-v1-20261011` and changes a file with the same path, `forward/source_attestation_verifier_v1.py`, but uses a different attestation schema/API: `snapshot_path`, `attestation_path`, `expected_context`, signed retrieval metadata and redirect chain, plus freshness enforcement (24-hour max age, 5-minute future skew).
- These are distinct branch histories and incompatible verifier contracts. Their separate green CI runs do **not** prove the two changes work together. Avoid selecting or merging either implementation based only on the green status.

## Required next surgery — forward only
1. Choose one canonical attestation schema/API and explicitly port the freshness rules into that implementation.
2. Add integration tests for signature validation + raw-byte digest + expected context/scope + requested/final URL and full redirect chain + retrieval timestamp freshness + unknown key/missing external trust root + coordinated registry/lock tampering + fail-closed pre-network/no-session-write behavior.
3. Run the combined targeted workflow on the exact resulting head SHA; record run URL, job, conclusion and test count.
4. Keep PRs Draft/unmerged until an independent human review and external trust-root governance are established.
5. Obtain authoritative Tabdeal documentation or written clarification for `special_margin/broadcast/` inner `trade.sequence`. A valid attestation of generic docs does not itself prove undocumented sequence semantics.
6. Keep Tabdeal `trade.sequence=unknown/opaque`, production evidence pin unset, gap detection disabled, and live observation/trading blocked.
7. The two Toobit support replies are supplemental design context only; never generalize them to Tabdeal.
8. Do not repeat the 42-record reconciliation, alter historical records/Winners/thresholds/evidence logic, perform feature extraction/Effective Evidence, start the collector, or deploy.

## Gate status
- Existing isolated CI jobs inspected: PASS on the exact heads listed above.
- Combined verifier + freshness integration: NOT VERIFIED.
- Independently governed production trust root: NOT VERIFIED.
- Official Tabdeal `trade.sequence` semantics: NOT VERIFIED.
- Production evidence pin: UNSET.
- Live collector/observation/trading: BLOCKED.
