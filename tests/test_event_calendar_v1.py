import json
import unittest
from datetime import date

from core.market_intelligence.event_calendar_v1 import parse_fomc_calendar, parse_stat_calendar


class FedEventCalendarTests(unittest.TestCase):
    def test_stat_calendar_filters_relevant_events_and_converts_eastern_time(self):
        payload = json.dumps({
            "events": [
                {"title": "G.17 - Industrial Production and Capacity Utilization", "time": "9:15 a.m.", "month": "2026-11", "days": "17", "type": "Stat"},
                {"title": "G.19 - Consumer Credit", "time": "3:00 p.m.", "month": "2026-11", "days": "6", "type": "Stat"},
                {"title": "CP - Commercial Paper", "time": "1:00 p.m.", "month": "2026-11", "days": "4", "type": "Stat"},
                {"title": "Z.1 - Financial Accounts of the United States", "time": "12:00 p.m.", "month": "2026-12", "days": "10", "type": "Stat"},
            ]
        }).encode()
        events = parse_stat_calendar(payload, today=date(2026, 11, 3), horizon_days=30, source_sha256="a" * 64)
        self.assertEqual([x["title"] for x in events], [
            "G.19 - Consumer Credit",
            "G.17 - Industrial Production and Capacity Utilization",
        ])
        self.assertEqual(events[0]["scheduled_at_utc"], "2026-11-06T20:00:00Z")
        self.assertEqual(events[1]["scheduled_at_utc"], "2026-11-17T14:15:00Z")
        self.assertEqual(events[1]["impact_rating"], "unrated")

    def test_multi_day_stat_release_is_kept_as_a_date_range(self):
        payload = json.dumps({"events": [
            {"title": "Senior Credit Officer Opinion Survey (SCOOS)", "time": "2:00 p.m.",
             "month": "2026-11", "days": "19-20", "type": "Stat"}
        ]}).encode()
        events = parse_stat_calendar(payload, today=date(2026, 11, 3), horizon_days=30, source_sha256="b" * 64)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["start_date"], "2026-11-19")
        self.assertEqual(events[0]["end_date"], "2026-11-20")
        self.assertEqual(events[0]["time_precision"], "exact_local_time")

    def test_fomc_schedule_has_dates_but_does_not_invent_statement_time(self):
        html = b"""<!doctype html><html><body>
        <h4><a id='2026'>2026 FOMC Meetings</a></h4>
        <div class='row fomc-meeting'>
          <div class='fomc-meeting__month'><strong>December</strong></div>
          <div class='fomc-meeting__date'>8-9</div>
        </div>
        <h4><a id='2027'>2027 FOMC Meetings</a></h4>
        <div class='row fomc-meeting'>
          <div class='fomc-meeting__month'><strong>January</strong></div>
          <div class='fomc-meeting__date'>26-27</div>
        </div></body></html>"""
        events = parse_fomc_calendar(html, today=date(2026, 11, 3), horizon_days=60, source_sha256="c" * 64)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["start_date"], "2026-12-08")
        self.assertEqual(events[0]["end_date"], "2026-12-09")
        self.assertIsNone(events[0]["local_time"])
        self.assertEqual(events[0]["time_precision"], "date_range")
        self.assertEqual(events[1]["start_date"], "2027-01-26")


if __name__ == "__main__":
    unittest.main()
