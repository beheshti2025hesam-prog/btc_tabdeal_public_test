"""
HES Trade Agent - Data Engine v1.
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
    """Read -> validate -> normalize -> audit -> deduplicate -> order."""
    def __init__(self, reader=None, validator=None, normalizer=None, deduplicator=None, integrity_audit=None):
        self.reader = reader or RawDataReader()
        self.validator = validator or RawDataValidator()
        self.normalizer = normalizer or RawDataNormalizer()
        self.deduplicator = deduplicator or TradeDeduplicator()
        self.integrity_audit = integrity_audit or IntegrityAudit()
        self.last_quality_report = None

    def load(self) -> List[CanonicalTrade]:
        canonical = []
        total = valid = invalid = 0
        for row in self.reader.read_all():
            total += 1
            errors = self.validator.validate_row(row)
            if errors:
                invalid += 1
                continue
            valid += 1
            canonical.append(self.normalizer.normalize_row(row))
        validation = {"total_rows": total, "valid_rows": valid, "invalid_rows": invalid}
        integrity = self.integrity_audit.audit(canonical)
        unique = self.deduplicator.deduplicate(canonical)
        ordered = sorted(unique, key=lambda trade: trade.timestamp)
        self.last_quality_report = DataQualityReport(
            total_trades=len(canonical), validation=validation,
            integrity=integrity["groups"],
            metadata={"deduplicated_trades": len(ordered)},
        )
        return ordered
