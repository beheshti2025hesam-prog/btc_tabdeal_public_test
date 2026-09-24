import csv
import tempfile
import unittest
from pathlib import Path
from datetime import timezone

from core.data_engine.engine import DataEngine
from core.data_engine.integrity import IntegrityAudit
from core.data_engine.normalizer import RawDataNormalizer
from core.data_engine.reader import RawDataReader
from core.data_engine.validator import RawDataValidator


def raw_row(sequence="100", updated="2026-09-24T00:00:00Z"):
    return {
        "symbol": "BTC_USDT",
        "price": "100000.5",
        "amount": "0.01",
        "side": "buy",
        "updated": updated,
        "sequence": sequence,
    }


class DataEngineFoundationTests(unittest.TestCase):
    def test_validator_accepts_valid_row(self):
        self.assertEqual(RawDataValidator().validate_row(raw_row()), [])

    def test_validator_rejects_invalid_numeric_fields(self):
        row = raw_row(sequence="bad")
        row["price"] = "bad"
        row["amount"] = "bad"
        errors = RawDataValidator().validate_row(row)
        self.assertIn("Invalid price", errors)
        self.assertIn("Invalid amount", errors)
        self.assertIn("Invalid sequence", errors)

    def test_normalizer_converts_timestamp_to_utc_and_builds_event_id(self):
        trade = RawDataNormalizer().normalize_row(
            raw_row(updated="2026-09-24T03:30:00+03:30")
        )
        self.assertEqual(trade.timestamp.tzinfo, timezone.utc)
        self.assertEqual(trade.timestamp.hour, 0)
        self.assertEqual(trade.timestamp.minute, 0)
        self.assertEqual(len(trade.event_id), 64)

    def test_reader_discovers_active_and_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "trades.csv"
            archive = root / "archive"
            archive.mkdir()
            header = ["symbol", "price", "amount", "side", "updated", "sequence"]
            for path in (active, archive / "a.csv", archive / "b.csv"):
                with path.open("w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(header)
            reader = RawDataReader(str(active), str(archive))
            self.assertEqual(
                reader.discover_files(),
                [str(active), str(archive / "a.csv"), str(archive / "b.csv")],
            )

    def test_integrity_detects_duplicate_and_gap(self):
        normalizer = RawDataNormalizer()
        trades = [
            normalizer.normalize_row(raw_row(sequence="100")),
            normalizer.normalize_row(raw_row(sequence="102", updated="2026-09-24T00:00:01Z")),
            normalizer.normalize_row(raw_row(sequence="102", updated="2026-09-24T00:00:01Z")),
        ]
        report = IntegrityAudit().audit(trades)["groups"][("tabdeal", "BTC_USDT")]
        self.assertEqual(report["duplicate_sequence_count"], 1)
        self.assertEqual(report["sequence_gap_count"], 1)

    def test_engine_deduplicates_orders_and_preserves_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "trades.csv"
            archive = root / "archive"
            archive.mkdir()
            header = ["symbol", "price", "amount", "side", "updated", "sequence"]
            rows = [
                raw_row(sequence="102", updated="2026-09-24T00:00:02Z"),
                raw_row(sequence="100", updated="2026-09-24T00:00:00Z"),
                raw_row(sequence="100", updated="2026-09-24T00:00:00Z"),
                raw_row(sequence="101", updated="2026-09-24T00:00:01Z"),
            ]
            with active.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=header)
                writer.writeheader()
                writer.writerows(rows)
            before = active.read_bytes()

            engine = DataEngine(reader=RawDataReader(str(active), str(archive)))
            result = engine.load()

            self.assertEqual([t.sequence for t in result], [100, 101, 102])
            self.assertEqual(len(result), 3)
            self.assertEqual(active.read_bytes(), before)
            self.assertEqual(engine.last_quality_report.validation["total_rows"], 4)
            self.assertEqual(engine.last_quality_report.validation["invalid_rows"], 0)
            self.assertEqual(engine.last_quality_report.metadata["deduplicated_trades"], 3)


if __name__ == "__main__":
    unittest.main()
