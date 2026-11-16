"""
HES Trade Agent - Read-only Data Integrity Audit.
"""
from collections import defaultdict
from typing import Iterable

from core.models.trade import CanonicalTrade


class IntegrityAudit:
    """Audit row/event integrity; opaque sequence metadata is not analyzed."""
    def audit(self, trades: Iterable[CanonicalTrade]) -> dict:
        groups = defaultdict(list)
        for trade in trades:
            groups[(trade.exchange, trade.symbol)].append(trade)
        reports = {key: self._audit_group(group) for key, group in groups.items()}
        return {"total_trades": sum(r["total_trades"] for r in reports.values()), "groups": reports}

    @staticmethod
    def _audit_group(trades: list[CanonicalTrade]) -> dict:
        by_timestamp = sorted(trades, key=lambda trade: trade.timestamp)
        event_ids = {t.event_id for t in trades}
        sequenced = [t for t in trades if t.sequence is not None]
        return {
            "total_trades": len(trades),
            "unique_event_ids": len(event_ids),
            "duplicate_event_id_count": len(trades) - len(event_ids),
            "sequence_values_present": len(sequenced),
            "sequence_analysis_status": "OPAQUE_METADATA_NOT_ANALYZED",
            "unique_sequences": None,
            "duplicate_sequence_count": None,
            "sequence_gap_count": None,
            "sequence_gap_total": None,
            "largest_sequence_gap": None,
            "min_sequence": None,
            "max_sequence": None,
            "backward_sequence_count": None,
            "timestamp_backward_count": None,
            "first_timestamp": by_timestamp[0].timestamp if by_timestamp else None,
            "last_timestamp": by_timestamp[-1].timestamp if by_timestamp else None,
        }
