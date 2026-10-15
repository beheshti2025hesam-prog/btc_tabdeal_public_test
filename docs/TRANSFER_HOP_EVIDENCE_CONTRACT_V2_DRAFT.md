# Transfer Hop Evidence Contract v2 (Draft; fail-closed)

Status: proposal only. This document does not authorize collection, sequence interpretation, or trading.

## Required evidence per hop

A URL list is not proof of a transfer. Every hop MUST have a signed, canonical record containing:
- zero-based hop_index and request_id unique within the transfer;
- request_url, request_method, request_timestamp;
- response_status, response_timestamp, response_url (the URL actually observed after the hop);
- response_headers_digest and response_body_sha256 (hashes of captured raw bytes, with a documented canonicalization rule for headers);
- previous_hop_record_sha256 (null only for the first hop);
- TLS peer identity evidence: hostname, certificate/SPKI fingerprint, validation result, and observation timestamp;
- capture agent identity/version and evidence artifact path;
- transfer_id, expected_commit, market_scope, key_id, signature_algorithm, signature_b64.

The signed bytes MUST cover every field above except signature_b64, using one specified canonical JSON encoding. Raw response bytes and raw header capture MUST be retained as immutable artifacts; hashes alone do not prove what was captured unless the artifacts are available and re-hash correctly.

## Chain invariants

1. Hop indexes are contiguous from 0; duplicate, missing, or reordered hops fail closed.
2. Each hop's request_url equals the prior hop's observed response_url only when the recorded redirect semantics explicitly establish that transition; otherwise the chain is rejected as ambiguous.
3. The final hop's response_url must equal the declared source_url, and the final response's body hash must equal raw_sha256.
4. Every hostname is checked against an independently maintained HTTPS hostname allowlist. HTTPS syntax alone is not identity proof.
5. Reject userinfo, fragments, malformed ports, non-HTTPS URLs, whitespace/control characters, unapproved hosts, unexpected ports, and unapproved scheme/host changes.
6. Every hop signature must validate against a pinned trusted key registry; unknown/revoked keys fail closed. The signature must bind the full hop record and transfer_id.
7. Evidence must match the exact expected commit, evidence path, market scope, and freshness window.
8. Missing response artifacts, mismatched hashes, invalid signatures, changed destinations, missing hops, inconsistent response metadata, or any ambiguity MUST fail closed without mutating existing evidence.
9. Tests must assert the specific rejection and verify the pre-existing evidence bytes remain unchanged.

## Required adversarial tests

- forged/unapproved destination hostname;
- response status/URL/body inconsistent with captured response;
- missing intermediate hop and duplicated/reordered hop index;
- destination mutation after signing;
- invalid signature, wrong key, revoked key, and signature covering only a subset of fields;
- redirect loop, scheme/port/hostname changes, and userinfo/fragment tricks;
- raw response or headers artifact missing or changed after capture;
- final response URL differs from declared source URL;
- exact commit/path/market mismatch and stale/future timestamp;
- valid multi-hop chain accepted only when every record, signature, artifact hash, and transition agrees.

## Gate

This v2 contract remains unimplemented until verifier, hostile tests, and CI are updated and pass on the exact resulting SHA. Passing this contract does not establish the meaning of Tabdeal `trade.sequence`. Keep ordering/gap detection and trading disabled until an official, market-and-channel-specific contract is independently evidenced.
