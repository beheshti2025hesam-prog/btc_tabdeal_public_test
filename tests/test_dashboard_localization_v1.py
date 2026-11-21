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
        self.assertIn('Copyright © HES Trade Agent. All rights reserved.', dashboard.HTML)
        self.assertIn('aria-label="HES Trade Agent — Designer and Owner"', dashboard.HTML)
        self.assertIn('alt="HES Trade Agent. Copyright © HES Trade Agent. All rights reserved. SEYED HESAMEDDIN BEHESHTI SHIRAZI — Designer &amp; Owner"', dashboard.HTML)
        self.assertIn('Copyright (c) 2025 TradingView, Inc.', dashboard.HTML)
        self.assertIn('class="brand-footer-art"', dashboard.HTML)

    def test_locale_persistence_direction_and_fallback_are_client_side(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        css = (root / "web" / "static" / "dashboard.css").read_text(encoding="utf-8")
        self.assertIn("hes-dashboard-locale-v1", script)
        self.assertIn("Chart overlays", script)
        self.assertIn("Chart-Overlays", script)
        self.assertIn("اندیکاتورهای روی نمودار", script)
        self.assertIn('id="showEma"', dashboard.HTML)
        self.assertIn('id="showVwap"', dashboard.HTML)
        self.assertIn('id="chartIndicatorStatus"', dashboard.HTML)
        self.assertIn("localStorage.getItem(KEY)", script)
        self.assertIn("localStorage.setItem(KEY,locale)", script)
        self.assertIn("return LOCALES.includes(value)?value:'en'", script)
        self.assertIn("locale==='fa'?'rtl':'ltr'", script)
        self.assertIn("const ORIGINAL_TEXT=new WeakMap(),LAST_TEXT=new WeakMap()", script)
        self.assertIn("if(locale==='en')return text", script)
        self.assertNotIn("const maps={}; const reverse={};", script)
        self.assertIn('[dir="rtl"] .journal-table', css)
        self.assertIn('[dir="rtl"] #chart{direction:ltr}', css)

    def test_mapped_symbol_scope_and_timeframe_roles_are_translated_in_all_locales(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        for symbol in ('BTCUSDT', 'ETHUSDT', 'SOLUSDT'):
            self.assertIn(f'value="{symbol}"', dashboard.HTML)
        for translated in (
            'پژوهش فقط‌خواندنی', 'Nur lesende Forschung', 'Recherche en lecture seule',
            'نمودار بازار و اندیکاتورها', 'Marktchart und Indikatoren',
            'Le graphique de marché et les indicateurs',
            'صرفاً توصیفی', 'NUR BESCHREIBEND', 'DESCRIPTIF UNIQUEMENT',
        ):
            self.assertIn(translated, script)
        dashboard_source = (root / 'web' / 'dashboard.py').read_text(encoding='utf-8')
        self.assertIn('DESCRIPTIVE_ONLY_NOT_YET_VALIDATED_FOR_SYMBOL', dashboard_source)
        self.assertIn('Strategy/Mother decision panels remain BTC-canonical', dashboard.HTML)

    def test_localization_does_not_rewrite_api_payloads_or_machine_values(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        script = (root / "web" / "static" / "dashboard.js").read_text(encoding="utf-8")
        self.assertIn("fetchWithTimeout('/api/candles?'+q", script)
        self.assertIn("fetchWithTimeout('/api/precision-entry'", script)
        self.assertIn("fetchWithTimeout('/api/strategy-v2'", script)
        self.assertIn("fetchWithTimeout('/api/mother'", script)
        self.assertIn("fetchWithTimeout('/api/news'", script)
        self.assertIn("fetchWithTimeout('/api/journal?limit=50'", script)
        for machine_value in ("NO_TRADE", "BLOCKED", "VERIFIED", "1m", "15m", "4h"):
            self.assertIn(machine_value, script)
        self.assertIn("BTCUSDT", dashboard.HTML)
        self.assertIn("API payloads, machine enums, symbols and evidence remain untouched", script)
        for api_id in ("price", "peReasons", "v2Decision", "motherStages", "newsSummary", "newsItems", "journalRows"):
            self.assertRegex(dashboard.HTML, rf'id="{api_id}" data-no-translate')
        self.assertIn('class="brand-footer-art"', dashboard.HTML)
        self.assertIn('alt="HES Trade Agent. Copyright © HES Trade Agent. All rights reserved.', dashboard.HTML)
        self.assertIn('Copyright (c) 2025 TradingView, Inc.', dashboard.HTML)


    def test_official_hes_brand_assets_are_integrated_as_header_and_footer(self):
        root = Path(dashboard.__file__).resolve().parents[1]
        emblem = root / "web" / "static" / "hes-official-emblem.png"
        logo = root / "web" / "static" / "hes-official-logo.png"
        self.assertTrue(emblem.is_file())
        self.assertTrue(logo.is_file())
        self.assertIn('href="/static/hes-official-emblem.png" type="image/png"', dashboard.HTML)
        self.assertIn('class="brand-mark" src="/static/hes-official-emblem.png"', dashboard.HTML)
        self.assertIn('href="/static/hes-official-logo.png"', dashboard.HTML)
        self.assertIn('src="/static/hes-official-logo.png"', dashboard.HTML)
        dashboard_source = (root / "web" / "dashboard.py").read_text(encoding="utf-8")
        self.assertIn('"/static/hes-official-emblem.png": ("hes-official-emblem.png", "image/png")', dashboard_source)
        self.assertIn('"/static/hes-official-logo.png": ("hes-official-logo.png", "image/png")', dashboard_source)
        self.assertIn(".brand-lockup", (root / "web" / "static" / "dashboard.css").read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
