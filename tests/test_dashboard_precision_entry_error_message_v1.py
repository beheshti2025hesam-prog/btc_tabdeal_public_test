from __future__ import annotations

import unittest
from pathlib import Path

import web.dashboard as dashboard


class DashboardPrecisionEntryErrorMessageTests(unittest.TestCase):
    def test_precision_entry_prefers_reason_codes_over_generic_exception_name(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("function precisionEntryFailureMessage(payload)", script)
        self.assertIn("payload?.reason_codes", script)
        self.assertIn("throw Error(precisionEntryFailureMessage(v))", script)
        self.assertNotIn("throw Error(v.reason||'Multi-timeframe evidence unavailable')", script)

    def test_precision_entry_failure_copy_covers_all_supported_locales(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        for phrase in (
            "Multi-timeframe evidence unavailable. Precision Entry remains blocked.",
            "شواهد چندبازه‌ای در دسترس نیست؛ ورود دقیق مسدود می‌ماند.",
            "Multi-Timeframe-Nachweise nicht verfügbar. Der Präzisionseinstieg bleibt blockiert.",
            "Preuves multi-unités indisponibles. L’entrée précise reste bloquée.",
        ):
            self.assertIn(phrase, script)
        self.assertIn("codes.join(' · ')", script)


if __name__ == "__main__":
    unittest.main()
