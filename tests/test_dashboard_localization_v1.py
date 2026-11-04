from __future__ import annotations

import unittest
from pathlib import Path

import web.dashboard as dashboard


class DashboardLocalizationTests(unittest.TestCase):
    def test_four_language_selector_defaults_to_english(self):
        page = dashboard.HTML
        self.assertIn('<html lang="en">', page)
        self.assertIn('id="languageSelect"', page)
        for option in (
            '<option value="en">English</option>',
            '<option value="fa">فارسی</option>',
            '<option value="de">Deutsch</option>',
            '<option value="fr">Français</option>',
        ):
            self.assertIn(option, page)
        self.assertNotIn('<option value="es">', page)

    def test_english_copyright_owner_is_present_and_separate_from_vendor_notice(self):
        self.assertIn(
            '''Copyright © HES Trade Agent. All rights reserved.\nDesigned and Owned by\nSEYED HESAMEDDIN BEHESHTI SHIRAZI\nDesigner & Owner''',
            dashboard.HTML,
        )
        self.assertIn('Copyright (c) 2025 TradingView, Inc.', dashboard.HTML)
        self.assertIn('lang="en" dir="ltr"', dashboard.HTML)

    def test_locale_persistence_direction_and_fallback_are_client_side(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        css = (root / "web" / "static" / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("hes-dashboard-locale-v1", script)
        self.assertIn("localStorage.getItem(KEY)", script)
        self.assertIn("localStorage.setItem(KEY,locale)", script)
        self.assertIn("return LOCALES.includes(value)?value:'en'", script)
        self.assertIn("locale==='fa'?'rtl':'ltr'", script)
        self.assertIn('[dir="rtl"] .journal-table', css)
        self.assertIn('[dir="rtl"] #chart{direction:ltr}', css)

    def test_localization_does_not_rewrite_api_payloads_or_machine_values(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/candles?'+q", script)
        self.assertIn("fetch('/api/precision-entry'", script)
        self.assertIn("fetch('/api/strategy-v2'", script)
        self.assertIn("fetch('/api/mother'", script)
        self.assertIn("fetch('/api/news'", script)
        self.assertIn("fetch('/api/journal?limit=50'", script)
        for machine_value in ("NO_TRADE", "BLOCKED", "VERIFIED", "1m", "15m", "4h"):
            self.assertIn(machine_value, script)
        self.assertIn("BTCUSDT", dashboard.HTML)
        self.assertIn("API payloads, machine enums, symbols and evidence remain untouched", script)
        for api_id in ("price", "peReasons", "v2Decision", "motherStages", "newsSummary", "newsItems", "journalRows"):
            self.assertRegex(dashboard.HTML, rf'id="{api_id}" data-no-translate')
        self.assertIn('class="copyright" lang="en" dir="ltr" data-no-translate', dashboard.HTML)


if __name__ == "__main__":
    unittest.main()
