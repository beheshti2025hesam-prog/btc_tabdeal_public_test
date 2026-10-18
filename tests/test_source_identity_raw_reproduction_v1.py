"""CI test: independently reproduce the pinned 42 historical records."""
from scripts.verify_source_identity_reconciliation_v1 import main


def test_all_42_manifest_records_reproduce_from_pinned_raw_sources() -> None:
    main()
