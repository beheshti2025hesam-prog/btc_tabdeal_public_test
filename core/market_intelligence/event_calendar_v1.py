"""Official Federal Reserve scheduled-release calendar (informational only)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

FED_STATCALENDAR_URL = "https://www.federalreserve.gov/data/statcalendar.json"
FED_FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_TZ = ZoneInfo("America/New_York")
MAX_BYTES = 1_000_000
RELEVANT_STAT_TERMS = (
    "industrial production", "consumer credit", "financial accounts",
    "senior loan officer opinion survey", "senior credit officer opinion survey",
    "money stock measures", "assets and liabilities of commercial banks",
    "factors affecting reserve balances",
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, accept: str) -> bytes:
    request = Request(url, headers={
        "User-Agent": "HES-Trade-Agent-News/1.0",
        "Accept": accept,
    })
    try:
        with build_opener(_NoRedirect()).open(request, timeout=8) as response:
            payload = response.read(MAX_BYTES + 1)
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError(f"FED_CALENDAR_SOURCE_UNAVAILABLE:{type(exc).__name__}") from exc
    if len(payload) > MAX_BYTES:
        raise ValueError("FED_CALENDAR_PAYLOAD_TOO_LARGE")
    return payload


def _parse_day_range(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*", value or "")
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if not 1 <= start <= 31 or not start <= end <= 31:
        return None
    return start, end


def _parse_local_time(value: str) -> time | None:
    cleaned = re.sub(r"\.", "", (value or "").strip()).upper()
    if not cleaned:
        return None
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(cleaned, fmt).time()
        except ValueError:
            pass
    return None


def _in_horizon(start: date, end: date, today: date, horizon_end: date) -> bool:
    return end >= today and start <= horizon_end


def _make_event(*, source_id: str, title: str, start_date: date, end_date: date,
                local_time: time | None, source_url: str, payload_sha256: str,
                event_type: str) -> dict:
    local_dt = datetime.combine(start_date, local_time, tzinfo=FED_TZ) if local_time else None
    identity = "|".join((source_id, title, start_date.isoformat(), end_date.isoformat(),
                         local_time.isoformat() if local_time else "date-only"))
    return {
        "event_id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24],
        "source_id": source_id,
        "title": title,
        "event_type": event_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "local_time": local_time.strftime("%H:%M") if local_time else None,
        "timezone": "America/New_York",
        "scheduled_at_utc": local_dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z") if local_dt else None,
        "time_precision": "exact_local_time" if local_time else ("date_range" if start_date != end_date else "date_only"),
        "impact_rating": "unrated",
        "source_url": source_url,
        "source_payload_sha256": payload_sha256,
    }


class _FOMCParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.div_depth = 0
        self.row_depth = None
        self.current_field = None
        self.cell_text = ""
        self.row = {}
        self.year = None
        self.in_h4 = False
        self.heading = ""
        self.rows = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag == "h4":
            self.in_h4 = True
            self.heading = ""
        if tag == "div":
            self.div_depth += 1
            if "row" in classes and "fomc-meeting" in classes:
                self.row_depth = self.div_depth
                self.row = {}
            elif self.row_depth is not None and "fomc-meeting__month" in classes:
                self.current_field = "month"
                self.cell_text = ""
            elif self.row_depth is not None and "fomc-meeting__date" in classes:
                self.current_field = "days"
                self.cell_text = ""

    def handle_data(self, data):
        if self.in_h4:
            self.heading += data
        if self.current_field:
            self.cell_text += data

    def handle_endtag(self, tag):
        if tag == "h4":
            match = re.search(r"(20\d{2})\s+FOMC Meetings", self.heading)
            if match:
                self.year = int(match.group(1))
            self.in_h4 = False
        if tag == "div":
            if self.current_field:
                self.row[self.current_field] = " ".join(self.cell_text.split())
                self.current_field = None
                self.cell_text = ""
            if self.row_depth == self.div_depth:
                if self.year and self.row.get("month") and self.row.get("days"):
                    self.rows.append({"year": self.year, **self.row})
                self.row_depth = None
                self.row = {}
            self.div_depth = max(0, self.div_depth - 1)


def _month_number(name: str) -> int | None:
    try:
        return datetime.strptime(name.strip(), "%B").month
    except ValueError:
        return None


def parse_fomc_calendar(payload: bytes, *, today: date, horizon_days: int, source_sha256: str) -> list[dict]:
    parser = _FOMCParser()
    parser.feed(payload.decode("utf-8-sig", errors="strict"))
    horizon_end = today + timedelta(days=horizon_days)
    events = []
    for row in parser.rows:
        month = _month_number(row["month"])
        days = _parse_day_range(row["days"])
        if not month or not days:
            continue
        start_day, end_day = days
        try:
            start = date(row["year"], month, start_day)
            end = date(row["year"], month, end_day)
        except ValueError:
            continue
        if not _in_horizon(start, end, today, horizon_end):
            continue
        events.append(_make_event(
            source_id="fed_fomc_schedule",
            title="Federal Open Market Committee meeting",
            start_date=start, end_date=end, local_time=None,
            source_url=FED_FOMC_URL, payload_sha256=source_sha256,
            event_type="FOMC_MEETING",
        ))
    return events


def parse_stat_calendar(payload: bytes, *, today: date, horizon_days: int, source_sha256: str) -> list[dict]:
    try:
        data = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("FED_STATCALENDAR_INVALID_JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        raise ValueError("FED_STATCALENDAR_SCHEMA_INVALID")
    horizon_end = today + timedelta(days=horizon_days)
    events = []
    for item in data["events"]:
        if not isinstance(item, dict) or str(item.get("type", "")).casefold() != "stat":
            continue
        title = str(item.get("title", "")).strip()
        if not title or not any(term in title.casefold() for term in RELEVANT_STAT_TERMS):
            continue
        try:
            year, month = map(int, str(item.get("month", "")).split("-", 1))
        except ValueError:
            continue
        for token in str(item.get("days", "")).split(","):
            day_range = _parse_day_range(token)
            if not day_range:
                continue
            try:
                start = date(year, month, day_range[0])
                end = date(year, month, day_range[1])
            except ValueError:
                continue
            if not _in_horizon(start, end, today, horizon_end):
                continue
            local_time = _parse_local_time(str(item.get("time", "")))
            events.append(_make_event(
                source_id="fed_statcalendar",
                title=title, start_date=start, end_date=end, local_time=local_time,
                source_url=FED_STATCALENDAR_URL, payload_sha256=source_sha256,
                event_type="FED_STAT_RELEASE",
            ))
    return events


def fetch_fed_event_calendar(*, now: datetime | None = None, horizon_days: int = 30) -> dict:
    """Fetch official Fed statistical releases and FOMC dates; never infer impact."""
    if not 1 <= horizon_days <= 90:
        raise ValueError("horizon_days must be between 1 and 90")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = current.date()
    source_health = []
    failures = []
    events = []

    for source_id, url, accept, parser in (
        ("fed_statcalendar", FED_STATCALENDAR_URL, "application/json", parse_stat_calendar),
        ("fed_fomc_schedule", FED_FOMC_URL, "text/html", parse_fomc_calendar),
    ):
        try:
            payload = _fetch(url, accept)
            digest = hashlib.sha256(payload).hexdigest()
            parsed = parser(payload, today=today, horizon_days=horizon_days, source_sha256=digest)
            events.extend(parsed)
            source_health.append({"source_id": source_id, "status": "OK", "event_count": len(parsed), "payload_sha256": digest})
        except Exception as exc:
            code = str(exc)[:120] if isinstance(exc, ValueError) else type(exc).__name__
            failures.append({"source_id": source_id, "error_code": code})
            source_health.append({"source_id": source_id, "status": "FAILED", "event_count": 0, "error_code": code})

    events.sort(key=lambda item: (item["start_date"], item["local_time"] or "99:99", item["title"]))
    status = "OK" if not failures else ("PARTIAL" if events else "BLOCKED")
    result = {
        "schema": "hes.fed_event_calendar.v1",
        "status": status,
        "fetched_at": current.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "horizon_days": horizon_days,
        "timezone": "America/New_York",
        "coverage_note": "Federal Reserve statistical releases and FOMC meeting dates only. BLS CPI/jobs calendars are not included; the official BLS calendar endpoint is inaccessible from this VPS (HTTP 403).",
        "source_health": source_health,
        "source_failures": failures,
        "events": events,
        "impact_rating": "unrated",
        "news_or_calendar_alone_can_authorize_trade": False,
    }
    result["calendar_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result
