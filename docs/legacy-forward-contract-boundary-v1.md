# Legacy / forward data-contract boundary (v1)

## Rule

core.data_engine normalizes historical rows using updated and an integer sequence. Those rows may be useful for historical research, but that normalization is not proof of forward source identity, completeness, or ordering.

The forward path has a separate transport contract: source=tabdeal_ws_forward_v1, source_updated, and an opaque source sequence identity. Never promote a legacy row by renaming updated to source_updated, by converting its sequence, or by copying it into a forward-shaped dictionary. Only the read-only forward adapter may create forward evidence records from authenticated transport input.

## Boundary helper

forward.legacy_forward_contract_boundary_v1.require_forward_evidence_record is a fail-closed assertion for call sites and tests. It does not transform legacy data or authenticate the transport by itself. Production must still verify raw payload hashes, durable append-only receipt/ledger linkage, evidence-registry pinning, and independently authenticated review provenance.

## Sequence semantics

Do not use numeric gaps, coercion, or integer ordering as source-completeness or ordering proof unless a pinned source contract explicitly authorizes that meaning. Values such as 7, "7", and "007" must not be silently merged.
