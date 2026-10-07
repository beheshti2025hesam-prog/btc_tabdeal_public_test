"""Quality report -> snapshot identity -> append-only journal integration."""
from __future__ import annotations
from datetime import datetime
from .clean_observation_quality_report_v1 import CleanObservationQualityReportV1
from .observation_snapshot_identity_v1 import ObservationSnapshotIdentityV1
from .observation_journal_v1 import ObservationJournalV1


class ObservationJournalIntegrationV1:
    def __init__(self, journal: ObservationJournalV1):
        self.journal=journal
        self.identity=ObservationSnapshotIdentityV1()

    def record(self, *, forward_run_id: str, observed_at: datetime, regime: str, quality: str, gate_safe: bool):
        report=CleanObservationQualityReportV1.build(regime, quality, gate_safe)
        snapshot=self.identity.create(
            forward_run_id=forward_run_id,
            observed_at=observed_at,
            symbol="BTC_USDT",
            timeframe="15m",
            payload={"status":report.status,"regime":report.regime,"quality":report.quality,
                     "gate_safe":report.gate_safe,"report_state":report.report_state},
        )
        existing=self.journal.read()
        if any(x.snapshot_id==snapshot.snapshot_id for x in existing):
            raise ValueError("duplicate snapshot identity")
        self.journal.append(snapshot)
        return report, snapshot
