import pytest
from forward.legacy_forward_contract_boundary_v1 import (
    LEGACY_FORWARD_BOUNDARY_V1, LegacyForwardContractError,
    require_forward_evidence_record,
)

def test_legacy_csv_row_is_rejected():
    row = {"source": "raw_csv", "updated": "2026-01-01T00:00:00Z", "sequence": "7"}
    with pytest.raises(LegacyForwardContractError) as exc:
        require_forward_evidence_record(row)
    assert exc.value.code == LEGACY_FORWARD_BOUNDARY_V1

def test_renaming_legacy_timestamp_does_not_upgrade_provenance():
    row = {"source": "raw_csv", "source_updated": "2026-01-01T00:00:00Z", "sequence": "7"}
    with pytest.raises(LegacyForwardContractError):
        require_forward_evidence_record(row)

@pytest.mark.parametrize("sequence", [7, "7", "007"])
def test_forward_boundary_does_not_coerce_sequence(sequence):
    record = {"source": "tabdeal_ws_forward_v1", "source_updated": "2026-01-01T00:00:00Z", "sequence": sequence}
    assert require_forward_evidence_record(record) is None
    assert record["sequence"] == sequence

def test_forward_timestamp_is_required():
    with pytest.raises(LegacyForwardContractError) as exc:
        require_forward_evidence_record({"source": "tabdeal_ws_forward_v1", "sequence": "7"})
    assert exc.value.code == "FORWARD_SOURCE_TIMESTAMP_MISSING"
