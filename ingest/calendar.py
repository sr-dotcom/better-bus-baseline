"""Which service_ids run on a date, from calendar.txt and calendar_dates.txt.

GTFS reference: calendar.txt gives weekly patterns with inclusive start_date and end_date;
calendar_dates.txt adds (exception_type 1) or removes (2) a service on one date.
A feed may ship calendar_dates.txt only (the CATS feeds do), so calendar rows can be empty.
"""

from datetime import date

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def active_service_ids_from_rows(calendar: list[dict], calendar_dates: list[dict], day: date) -> set[str]:
    """Pure function. Rows are dicts of strings as in the GTFS files (dates as YYYYMMDD)."""
    ymd = day.strftime("%Y%m%d")
    weekday = _DAYS[day.weekday()]
    active = {r["service_id"] for r in calendar if r[weekday] == "1" and r["start_date"] <= ymd <= r["end_date"]}
    for r in calendar_dates:
        if r["date"] == ymd:
            if r["exception_type"] == "1":
                active.add(r["service_id"])
            elif r["exception_type"] == "2":
                active.discard(r["service_id"])
    return active


def _rows(con, table: str, feed_version: str) -> list[dict]:
    exists = con.execute("select count(*) from information_schema.tables where table_name = ?", [table]).fetchone()[0]
    if not exists:
        return []
    cur = con.execute(f"select * from {table} where feed_version = ?", [feed_version])
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def active_service_ids(con, feed_version: str, day: date) -> set[str]:
    """Thin DuckDB wrapper over the raw_calendar and raw_calendar_dates tables."""
    return active_service_ids_from_rows(
        _rows(con, "raw_calendar", feed_version), _rows(con, "raw_calendar_dates", feed_version), day
    )
