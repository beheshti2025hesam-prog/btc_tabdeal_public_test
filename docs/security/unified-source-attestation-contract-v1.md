# HES Unified Source Attestation Contract v1

Status: PROPOSAL ONLY — not an implementation, trust-root deployment, or approval to collect live data.

Target branch: `security/unified-attestation-contract-v1`
Design basis: compare the detached verifier proposed in PR #262 with the freshness/context hardening proposed in PR #259. Both are drafts and use incompatible verifier interfaces and attestation envelopes. This document deliberately does not choose either implementation as trusted.

## 1. Non-negotiable trust boundary

1. Trust roots are provisioned outside all PR-writable files and outside the evidence registry being verified.
2. The trusted key ID and public key must be read from one documented protected configuration interface. No fallback to a key included in the attestation, registry, lock file, test fixture, or branch is allowed.
3. Production verification must fail closed if configuration is missing, malformed, ambiguous, revoked, or inconsistent.
4. Private signing keys never belong in the repository, CI logs, artifacts, or source snapshots.
5. A valid signature proves only that the corresponding key signed the exact payload. It does not prove the signer retrieved an authentic source or that the source statement is true. The attestor process and its identity require separate governance and review.
6. No test-generated key, synthetic fixture, CI green status, or self-authored registry record may be represented as a production trust root or genuine exchange evidence.

## 2. One canonical envelope and payload

Before implementation, select and document exactly one versioned envelope. Do not silently accept both existing draft formats.

Required envelope semantics:
- explicit schema identifier and version;
- stable key identifier;
- detached Ed25519 signature over the exact canonical payload bytes;
- unambiguous payload encoding;
- strict parsing that rejects duplicate JSON keys and invalid encodings;
- explicit artifact SHA-256 over raw bytes, not normalized/re-serialized content;
- full reviewed commit SHA (40 lowercase hex for SHA-1 repositories, or 64 lowercase hex only where the repository actually uses SHA-256 object format);
- retrieval timestamp in UTC;
- requested URL, final URL, and complete redirect chain;
- retrieval tool and version;
- source context containing venue, product, endpoint, channel, message type, field, protocol version, reviewed commit, and contract version.

Canonicalization rules must be implemented once, documented, and tested with byte-level fixtures. The verifier must never guess whether a signature covers a JSON object, decoded payload, base64 string, or envelope.

## 3. Validation contract

The shared verifier must reject, at minimum:
- missing/unknown/revoked key ID, missing trust configuration, malformed key, malformed signature, or signature from another key;
- modified payload bytes, duplicate JSON keys, invalid payload encoding, unknown schema, or missing required fields;
- artifact byte change or mismatch between artifact bytes and declared SHA-256;
- stale evidence older than the configured maximum age (draft proposal: 24 hours) or future timestamp beyond allowed clock skew (draft proposal: 5 minutes); production values require explicit policy approval;
- naive/non-UTC timestamps and malformed timestamps;
- missing, empty, non-string, or unexpected source-context values;
- a reviewed commit that is malformed or differs from the exact commit under review;
- non-HTTPS URLs, URL credentials, malformed redirects, a broken redirect chain, or final URL inconsistent with the chain;
- lookalike or unauthorized source hosts. The allowed-host policy must be source-specific and exact; generic HTTPS validation alone is insufficient for claims about official exchange documentation;
- unexpected envelope/payload fields if the selected schema defines a closed schema.

All rejection paths must return a stable, non-sensitive error category; never echo secrets.

## 4. Independent source-attestor requirements

A verifier cannot prove retrieval provenance by itself. The separately governed attestor must:
- retrieve the source and preserve exact raw bytes plus request/final URL and redirect metadata;
- identify the retrieval tool and version;
- bind the result to the intended source scope and full reviewed commit;
- sign only after retrieval and validation complete;
- use a key whose custody, rotation, revocation, and identity are reviewed independently;
- emit an audit record that can be checked without trusting the PR under review.

The verifier and attestor must not share a mutable trust store controlled by the same change being verified.

## 5. Integration and migration rule

PR #259 and PR #262 currently present distinct implementations at the same Python module path but on different branch histories. Do not merge them by copying one file over the other. First agree the schema/interface and map each existing test to that contract. Then implement a single verifier and adapt tests/consumers in one dedicated branch. Keep legacy interfaces only behind an explicit migration adapter with tests; never infer the schema from payload shape.

## 6. Required integration test matrix

| Case | Expected result |
|---|---|
| Valid synthetic envelope, correct trusted test key, exact bytes and context | Pass only in isolated test |
| Missing trust root or key ID | Block |
| Unknown/revoked key ID or wrong public key | Block |
| Signature/payload tampering | Block |
| Artifact bytes changed while attestation unchanged | Block |
| Duplicate JSON key / ambiguous encoding | Block |
| Unknown schema or missing required field | Block |
| Stale timestamp / future timestamp / naive clock | Block |
| Missing or empty required context | Block |
| Malformed or wrong reviewed commit | Block |
| Commit differs from exact reviewed commit | Block |
| HTTP, credentials, lookalike host, malformed redirect chain | Block |
| Redirect final URL does not match signed final URL | Block |
| Attestation signed by test key presented as production evidence | Block |
| Registry/lock modified to point at attacker key | Block because trust root is external |
| Same evidence ID with changed bytes; duplicate ID; reordered records | Block unless a separately specified immutable versioning rule allows it |
| Missing evidence record / incomplete expected count | Block |
| Valid signature but false source assertion | Verifier alone cannot establish truth; independent attestor/source review required |

## 7. CI and acceptance gates

Run the full relevant suite on the exact candidate commit, including:
- existing sequence-capability registry tests;
- controlled observation runner integration tests;
- independent attestor tests;
- unified verifier positive/negative tests;
- duplicate-key, host allowlist, freshness, commit-binding, and tamper tests.

Record the full commit SHA, workflow run URL, job conclusions, test count, and review identity. A successful CI run is necessary but not sufficient.

Acceptance requires all of the following, none implied by this proposal:
1. exact schema and verifier interface approved;
2. protected trust-root provisioning documented and independently reviewed;
3. attestor custody and source-host policy reviewed;
4. all required tests pass on the exact commit;
5. a real independent human review is recorded on that commit;
6. registry completeness and every evidence record/hash are byte-verified;
7. all destructive tests pass.

Until all gates are independently evidenced: remain HOLD. Do not merge, pin a new hash as trusted, start live observation, unlock evidence, or enable trading.
