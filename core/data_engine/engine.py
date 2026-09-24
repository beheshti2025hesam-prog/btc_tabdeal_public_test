"""
Mother Agent - Data Engine
Data Engine v1.0
"""

from typing import List

from core.data_engine.deduplicator import TradeDeduplicator
from core.data_engine.integrity import IntegrityAudit
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.quality import DataQualityReport
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator
from core.models.trade import CanonicalTrade


class DataEngine:
    """
    Unified Raw Data processing pipeline.

    Pipeline:

    Reader
        ↓
    Validator
        ↓
    Normalizer
        ↓
    Integrity Audit
        ↓
    Deduplicator
        ↓
    Timestamp Ordering
        ↓
    Data Quality Report

    Raw Data is read-only and is never modified.
    """

    def __init__(
        self,
        reader: RawDataReader | None = None,
        validator: RawDataValidator | None = None,
        normalizer: RawDataNormalizer | None = None,
        deduplicator: TradeDeduplicator | None = None,
        integrity_audit: IntegrityAudit | None = None,
    ):
        self.reader = reader or RawDataReader()
        self.validator = validator or RawDataValidator()
        self.normalizer = normalizer or RawDataNormalizer()
        self.deduplicator = (
            deduplicator or TradeDeduplicator()
        )
        self.integrity_audit = (
            integrity_audit or IntegrityAudit()
        )

        self.last_quality_report: DataQualityReport | None = None

    def load(self) -> List[CanonicalTrade]:
        """
        Read, validate, normalize, audit, deduplicate,
        and timestamp-sort all available Raw Data.

        Invalid rows are skipped.

        Returns:
            A timestamp-ordered list of unique CanonicalTrade objects.
        """

        canonical_trades = []

        total_rows = 0
        valid_rows = 0
        invalid_rows = 0

        for row in self.reader.read_all():
            total_rows += 1

            errors = self.validator.validate_row(row)

            if errors:
                invalid_rows += 1
                continue

            valid_rows += 1

            trade = self.normalizer.normalize_row(row)
            canonical_trades.append(trade)

        validation_report = {
            "total_rows": total_rows,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
        }

        # Integrity must run BEFORE deduplication so that
        # duplicate events and duplicate sequences remain visible.
        integrity_result = self.integrity_audit.audit(
            canonical_trades
        )

        unique_trades = self.deduplicator.deduplicate(
            canonical_trades
        )

        ordered_trades = sorted(
            unique_trades,
            key=lambda trade: trade.timestamp,
        )

        self.last_quality_report = DataQualityReport(
            total_trades=len(canonical_trades),
            validation=validation_report,
            integrity=integrity_result["groups"],
            metadata={
                "deduplicated_trades": len(ordered_trades),
            },
        )

        return ordered_trades
