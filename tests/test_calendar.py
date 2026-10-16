from datetime import date

import duckdb

from ingest.calendar import active_service_ids, active_service_ids_from_rows

# Synthetic data. GTFS reference: calendar.txt start_date and end_date are inclusive;
# calendar_dates exception_type 1 = service added, 2 = service removed.
# 2026-09-07 is a Monday, so 2026-09-09 is a Wednesday, 2026-09-12 a Saturday.
WEEKDAY = {
    "service_id": "WK",
    "monday": "1", "tuesday": "1", "wednesday": "1", "thursday": "1", "friday": "1",
    "saturday": "0", "sunday": "0",
    "start_date": "20260908", "end_date": "20260930",
}  # fmt: skip
CAL = [WEEKDAY]


def run(day, cal=CAL, dates=()):
    return active_service_ids_from_rows(cal, list(dates), day)


def test_normal_weekday():
    assert run(date(2026, 9, 9)) == {"WK"}


def test_weekend_not_active():
    assert run(date(2026, 9, 12)) == set()


def test_added_date():
    # Saturday service added on a Saturday it would not normally run.
    assert run(date(2026, 9, 12), dates=[{"service_id": "SAT", "date": "20260912", "exception_type": "1"}]) == {"SAT"}


def test_removed_date():
    # Holiday: the weekday service is removed on Wednesday 2026-09-09.
    assert run(date(2026, 9, 9), dates=[{"service_id": "WK", "date": "20260909", "exception_type": "2"}]) == set()


def test_exception_only_affects_its_date():
    dates = [{"service_id": "WK", "date": "20260909", "exception_type": "2"}]
    assert run(date(2026, 9, 10), dates=dates) == {"WK"}


def test_start_date_boundary():
    # start_date 2026-09-08 (Tuesday) is inclusive; the Monday before is not in range.
    assert run(date(2026, 9, 8)) == {"WK"}
    assert run(date(2026, 9, 7)) == set()


def test_end_date_boundary():
    # end_date 2026-09-30 (Wednesday) is inclusive; Thursday 10-01 is out of range.
    assert run(date(2026, 9, 30)) == {"WK"}
    assert run(date(2026, 10, 1)) == set()


def test_calendar_dates_only_feed():
    dates = [{"service_id": "X", "date": "20261005", "exception_type": "1"}]
    assert run(date(2026, 10, 5), cal=[], dates=dates) == {"X"}
    assert run(date(2026, 10, 6), cal=[], dates=dates) == set()


def test_db_wrapper_filters_by_feed_and_handles_missing_calendar():
    con = duckdb.connect()
    con.execute(
        "create table raw_calendar_dates (service_id varchar, date varchar, exception_type varchar, feed_version varchar)"
    )
    con.execute("insert into raw_calendar_dates values ('A','20261005','1','v1'), ('B','20261005','1','v2')")
    assert active_service_ids(con, "v1", date(2026, 10, 5)) == {"A"}
    assert active_service_ids(con, "v2", date(2026, 10, 5)) == {"B"}
