"""Tests for the SQL layers (sql/staging, sql/intermediate, sql/marts) and the SQL test runner.

Two groups. The first builds the marts from the zips in data/raw/ (analysis.build.build_in_memory) and checks them
against the pure Python helpers in ingest/ (a second method) and against docs/known-answers.md. The second feeds a few
hand-made trips through the same SQL files in an empty DuckDB, so a threshold or a boundary can be set exactly.
"""

import tempfile
from pathlib import Path

import duckdb
import pytest

from analysis.build import build_in_memory, run_models, run_sql_tests
from ingest.gtfs_time import parse_gtfs_time
from ingest.headway import (
    PERIODS,
    departures_in_period,
    express_meets_standard,
    headway_stats,
    meets_standard,
    period_fail_reason,
    span_meets_standard,
)
from ingest.load_gtfs import FEEDS, load

# =====================================================================================================
# Group 1: marts built from data/raw/
# =====================================================================================================

LIMITS = {"15": 900, "30": 1800}


def test_sql_tests_pass_on_the_real_build():
    # The SQL tests in sql/tests/ return offending rows; none may come back.
    assert run_sql_tests(build_in_memory()) == []


def test_sql_tests_fail_loudly_when_a_mart_is_wrong():
    con = duckdb.connect()  # a private build: this test deletes a row
    with tempfile.TemporaryDirectory() as tmp:
        load(con, FEEDS, Path(tmp), "2026-10-16T00:00:00Z")
    run_models(con)
    assert run_sql_tests(con) == []
    con.execute("delete from route_compliance where route_short_name = '9' and date = date '2026-10-14'")
    failures = run_sql_tests(con)
    assert any("40_route_counts.sql" in f for f in failures)
    assert any("50_every_route_has_a_tier.sql" in f for f in failures)


def test_sql_time_parser_agrees_with_python_parser():
    # Staging parses GTFS times in SQL (gtfs_seconds); ingest/gtfs_time.py is the reference. Compare a sample of the
    # real times (every 20th distinct value) and hand-picked edge cases, including malformed ones.
    con = build_in_memory()
    real = [r[0] for r in con.execute("select distinct departure_time from raw_stop_times order by 1").fetchall()]
    edge = ["0:00:00", "00:00:00", "5:00:00", "05:00:00", "23:59:59", "24:00:00", "25:52:00", "26:01:00", "99:59:59"]
    bad = ["", "5:0:00", "12:60:00", "12:00:60", "1:2:3", "100:00:00", "12-00-00", " 12:00:00", "12:00:00 ", "ab:cd:ef"]
    for value in real[::20] + edge + bad:
        sql_value = con.execute("select gtfs_seconds(?)", [value]).fetchone()[0]
        try:
            expected = parse_gtfs_time(value)
        except ValueError:
            expected = None
        assert sql_value == expected, value
    assert len(real[::20]) > 50


def test_sql_time_formatter_round_trips():
    con = build_in_memory()
    for text in ["00:00:00", "04:50:00", "09:00:00", "25:52:00", "26:01:00"]:
        seconds = con.execute("select gtfs_seconds(?)", [text]).fetchone()[0]
        assert con.execute("select gtfs_hms(?)", [seconds]).fetchone()[0] == text


def test_periods_table_matches_the_python_periods():
    con = build_in_memory()
    sql = {r[0]: (r[1], r[2]) for r in con.execute("select period, start_s, end_s from periods").fetchall()}
    assert sql == PERIODS


def test_headway_mart_equals_python_helpers_for_every_row():
    # Second method: group the first-stop departures in Python and score them with ingest/headway.py. Every
    # route, direction, period and date in the mart must agree: count, median, max, both passes and both reasons.
    con = build_in_memory()
    deps = {}
    for fv, date, route, direction, dep in con.execute(
        "select feed_version, date, route_short_name, direction_id, departure_s from first_stop_departures"
    ).fetchall():
        deps.setdefault((fv, date, route, direction), []).append(dep)
    rows = con.execute(
        "select feed_version, date, route_short_name, direction_id, period, n_departures, headway_median_s, "
        "headway_max_s, covers_15, covers_30, passes_15, passes_30, reason_15, reason_30 from route_period_headway"
    ).fetchall()
    assert len(rows) > 1000
    for fv, date, route, direction, period, n, median, mx, c15, c30, p15, p30, r15, r30 in rows:
        in_period = departures_in_period(deps[(fv, date, route, direction)], period)
        stats = headway_stats(in_period)
        assert n == len(in_period)
        assert median == (None if stats is None else stats["median"])
        assert mx == (None if stats is None else stats["max"])
        key = (fv, date, route, direction, period)
        for covered, passes, reason, limit in ((c15, p15, r15, 900), (c30, p30, r30, 1800)):
            if covered:
                assert passes is meets_standard(stats, limit), key
                assert reason == period_fail_reason(stats, limit), key
            else:
                assert passes is None and reason is None, key


def test_span_mart_equals_python_helper_for_every_route():
    con = build_in_memory()
    rows = con.execute(
        "select first_departure_s, last_arrival_s, span_applicable, span_pass, span_start, span_end from route_span"
    ).fetchall()
    assert len(rows) > 250
    for start, end, applicable, passes, start_text, end_text in rows:
        assert (passes is span_meets_standard(start, end)) if applicable else (passes is None)
        assert parse_gtfs_time(start_text) == start and parse_gtfs_time(end_text) == end


# docs/known-answers.md section 4: [AM dir 0, AM dir 1, PM dir 0, PM dir 1, AM flow, PM flow, pass], Wed 2026-10-14.
EXPRESS_ANSWERS = {
    "40x": (2, 1, 0, 3, 2, 3, False),
    "41x": (3, 0, 0, 3, 3, 3, True),
    "46x": (3, 0, 0, 3, 3, 3, True),
    "48x": (7, 2, 2, 6, 7, 6, True),
    "52x": (3, 0, 0, 2, 3, 2, False),
    "53x": (6, 0, 1, 6, 6, 6, True),
    "61x": (6, 0, 0, 6, 6, 6, True),
    "62x": (3, 1, 1, 3, 3, 3, True),
    "63x": (7, 2, 1, 6, 7, 6, True),
    "64x": (6, 0, 1, 7, 6, 7, True),
    "74x": (2, 1, 1, 2, 2, 2, False),
    "77x": (7, 2, 1, 6, 7, 6, True),
    "85x": (2, 0, 1, 2, 2, 2, False),
    "88x": (3, 0, 0, 3, 3, 3, True),
}


@pytest.mark.parametrize(("route", "expected"), sorted(EXPRESS_ANSWERS.items()))
def test_express_mart_matches_all_14_known_answers(route, expected):
    am0, am1, pm0, pm1, am_flow, pm_flow, ok = expected
    con = build_in_memory()
    rows = {
        r[0]: r[1:]
        for r in con.execute(
            "select period, trips_direction_0, trips_direction_1, peak_flow_count, passes from express_peak_trips "
            "where date = date '2026-10-14' and route_short_name = ?",
            [route],
        ).fetchall()
    }
    assert rows["am_peak"][:3] == (am0, am1, am_flow)
    assert rows["pm_peak"][:3] == (pm0, pm1, pm_flow)
    assert express_meets_standard([am0, am1], [pm0, pm1]) is ok
    assert con.execute(
        "select express_pass from route_compliance where date = date '2026-10-14' and route_short_name = ?", [route]
    ).fetchone() == (ok,)


def test_route_compliance_is_consistent_with_the_headway_rows():
    # tier follows the sheet's order: 15-min if every scored direction passes 15 in both peaks, else 30-min if it
    # passes 30 in AM peak, midday and PM peak, else below standard. Recompute it from the headway rows.
    con = build_in_memory()
    rows = con.execute(
        "select feed_version, date, route_short_name, direction_id, period, passes_15, passes_30 "
        "from route_period_headway where day_type = 'weekday' and category = 'bus'"
    ).fetchall()
    verdict = {}
    for fv, date, route, _direction, _period, p15, p30 in rows:
        v = verdict.setdefault((fv, date, route), {"15": True, "30": True})
        if p15 is not None:
            v["15"] &= p15
        if p30 is not None:
            v["30"] &= p30
    tiers = {
        (r[0], r[1], r[2]): r[3]
        for r in con.execute(
            "select feed_version, date, route_short_name, tier from route_compliance "
            "where day_type = 'weekday' and category = 'bus' and not no_service_on_date"
        ).fetchall()
    }
    assert tiers.keys() == verdict.keys() and len(tiers) > 90
    for key, v in verdict.items():
        assert tiers[key] == ("15-min" if v["15"] else "30-min" if v["30"] else "below standard"), key


def test_before_after_matches_the_tiers_it_summarises():
    con = build_in_memory()
    order = {"15-min": 3, "30-min": 2, "below standard": 1, "no service on date": 0}
    rows = con.execute(
        "select route_short_name, category, tier_before, tier_after, change from before_after where category = 'bus'"
    ).fetchall()
    assert len(rows) == 48
    for route, _category, before, after, change in rows:
        if before == "no service on date" and after == "no service on date":
            expected = "same"
        elif before == "no service on date":
            expected = "new"
        elif after == "no service on date":
            expected = "gone"
        else:
            expected = "up" if order[after] > order[before] else "down" if order[after] < order[before] else "same"
        assert change == expected, route


# =====================================================================================================
# Group 2: hand-made feeds through the same SQL
# =====================================================================================================

RAW_COLUMNS = {
    "raw_agency": ["agency_id", "agency_name", "agency_url", "agency_timezone", "agency_lang", "agency_phone"],
    "raw_calendar_dates": ["service_id", "date", "exception_type"],
    "raw_routes": [
        "route_id",
        "route_short_name",
        "route_long_name",
        "route_desc",
        "route_type",
        "route_url",
        "route_color",
        "route_text_color",
    ],
    "raw_shapes": ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"],
    "raw_stop_times": [
        "trip_id",
        "arrival_time",
        "departure_time",
        "stop_id",
        "stop_sequence",
        "pickup_type",
        "drop_off_type",
        "timepoint",
    ],
    "raw_stops": [
        "stop_id",
        "stop_code",
        "stop_name",
        "stop_desc",
        "stop_lat",
        "stop_lon",
        "zone_id",
        "stop_url",
        "location_type",
        "parent_station",
    ],
    "raw_trips": ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id", "block_id", "shape_id"],
}

BEFORE, AFTER = "2026-09-10", "2026-09-29"
# weekday, saturday, sunday comparison dates of each feed
DATES = {
    BEFORE: {"weekday": "20260930", "saturday": "20260926", "sunday": "20260927"},
    AFTER: {"weekday": "20261014", "saturday": "20261017", "sunday": "20261018"},
}
WED_BEFORE, WED_AFTER = "2026-09-30", "2026-10-14"


def hms(seconds):
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def every(start, end, step):
    """Departure seconds from start to end (inclusive) every step seconds."""
    return list(range(start, end + 1, step))


def at(text):
    return parse_gtfs_time(text)


class Feeds:
    """Collects raw GTFS rows (all text, as the loader writes them) for both feed versions, then builds the marts."""

    def __init__(self):
        self.rows = {t: [] for t in RAW_COLUMNS}
        self.routes = set()
        self.services = set()
        self.n = 0

    def route(self, feed, name, route_type="3"):
        if (feed, name) not in self.routes:
            self.routes.add((feed, name))
            self.rows["raw_routes"].append(
                {"route_id": name, "route_short_name": name, "route_type": route_type, "feed_version": feed}
            )

    def day(self, feed, date, service=None, exception="1"):
        service = service or f"svc-{date}"
        if (feed, date, service, exception) not in self.services:
            self.services.add((feed, date, service, exception))
            self.rows["raw_calendar_dates"].append(
                {"service_id": service, "date": date, "exception_type": exception, "feed_version": feed}
            )
        return service

    def trip(self, feed, route, day_type, direction, dep, last_arr=None, route_type="3", stops=None, date=None):
        """One trip on the comparison date of day_type in feed. dep and last_arr are seconds; stops overrides the
        two default stops with (stop_sequence_text, arrival_s, departure_s) tuples."""
        self.route(feed, route, route_type)
        self.n += 1
        trip_id = f"t{self.n}"
        service = self.day(feed, date or DATES[feed][day_type])
        self.rows["raw_trips"].append(
            {
                "route_id": route,
                "service_id": service,
                "trip_id": trip_id,
                "direction_id": str(direction),
                "feed_version": feed,
            }
        )
        stops = stops or [("1", dep, dep), ("2", last_arr if last_arr is not None else dep + 600, dep + 600)]
        for seq, arr, depart in stops:
            self.rows["raw_stop_times"].append(
                {
                    "trip_id": trip_id,
                    "arrival_time": hms(arr),
                    "departure_time": hms(depart),
                    "stop_id": f"s{seq}",
                    "stop_sequence": seq,
                    "feed_version": feed,
                }
            )

    def trips(self, feed, route, day_type, direction, deps, **kw):
        for d in deps:
            self.trip(feed, route, day_type, direction, d, **kw)

    def build(self):
        con = duckdb.connect()
        for table, cols in RAW_COLUMNS.items():
            all_cols = [*cols, "feed_version", "loaded_at_utc"]
            con.execute(f"create table {table} ({', '.join(c + ' varchar' for c in all_cols)})")
            for row in self.rows[table]:
                con.execute(
                    f"insert into {table} values ({', '.join('?' * len(all_cols))})",
                    [row.get(c, "") for c in all_cols],
                )
        run_models(con)
        return con


def one(con, sql, *args):
    rows = con.execute(sql, list(args)).fetchall()
    assert len(rows) == 1, rows
    return rows[0]


def am_row(con, route, date=WED_AFTER, direction=0, period="am_peak"):
    cur = con.execute(
        "select n_departures as n, headway_median_s as median, headway_max_s as max, passes_15, passes_30, "
        "reason_15, reason_30 from route_period_headway "
        "where date = ? and route_short_name = ? and direction_id = ? and period = ?",
        [date, route, direction, period],
    )
    rows = cur.fetchall()
    assert len(rows) == 1, rows
    return dict(zip([c[0] for c in cur.description], rows[0]))


FEWER = "fewer than 2 departures in period"
ABOVE = "headway above standard"


def test_gap_of_exactly_15_minutes_passes_15_and_30():
    # MTC-06 3.7: "at least 15-minute peak service": a 15:00 median passes the 15-minute standard.
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, every(at("06:00:00"), at("07:30:00"), 900))
    assert am_row(f.build(), "A") == {
        "n": 7, "median": 900.0, "max": 900, "passes_15": True, "passes_30": True, "reason_15": None, "reason_30": None
    }  # fmt: skip


def test_median_one_second_over_15_minutes_fails_15_but_passes_30():
    # Gaps 900 and 901: even count, median = (900 + 901) / 2 = 900.5 > 900.
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, [at("06:00:00"), at("06:15:00"), at("06:30:01")])
    assert am_row(f.build(), "A") == {
        "n": 3, "median": 900.5, "max": 901, "passes_15": False, "passes_30": True, "reason_15": ABOVE, "reason_30": None
    }  # fmt: skip


def test_max_gap_does_not_fail_a_route_whose_median_passes():
    # Gaps 900, 900, 901: odd count, median 900 passes while the max is 901 (the max is reported, not scored).
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, [at("06:00:00"), at("06:15:00"), at("06:30:00"), at("06:45:01")])
    row = am_row(f.build(), "A")
    assert (row["median"], row["max"], row["passes_15"]) == (900.0, 901, True)


def test_gaps_of_exactly_30_minutes_pass_30_and_fail_15():
    # MTC-06 3.7: "at least 30-minute service on Common/local routes".
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, every(at("06:00:00"), at("08:00:00"), 1800))
    row = am_row(f.build(), "A")
    assert (row["median"], row["passes_15"], row["passes_30"], row["reason_15"], row["reason_30"]) == (
        1800.0,
        False,
        True,
        ABOVE,
        None,
    )


def test_median_one_second_over_30_minutes_fails_30():
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, [at("06:00:00"), at("06:30:00"), at("07:00:01")])  # gaps 1800, 1801
    row = am_row(f.build(), "A")
    assert row["median"] == 1800.5
    assert (row["passes_30"], row["reason_30"]) == (False, ABOVE)


def test_even_median_is_the_mean_of_the_two_middle_gaps():
    # Hand calculation: gaps 600, 900, 1200, 1500 in this order; sorted middle two are 900 and 1200 -> 1050.
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, [at("06:00:00") + s for s in (0, 600, 1500, 2700, 4200)])
    row = am_row(f.build(), "A")
    assert (row["median"], row["max"]) == (1050.0, 1500)


def test_two_trips_at_the_same_time_give_a_gap_of_zero():
    f = Feeds()
    f.trips(AFTER, "A", "weekday", 0, [at("06:00:00"), at("06:00:00"), at("06:15:00")])
    row = am_row(f.build(), "A")  # gaps 0 and 900: even count, median = (0 + 900) / 2 = 450
    assert (row["median"], row["max"]) == (450.0, 900)


def test_fewer_than_two_departures_has_no_headway_and_its_own_reason():
    f = Feeds()
    f.trips(AFTER, "ONE", "weekday", 0, [at("07:00:00"), at("12:00:00")])  # one departure in the AM peak
    f.trips(AFTER, "ZERO", "weekday", 0, [at("12:00:00")])  # none in the AM peak
    con = f.build()
    assert am_row(con, "ONE") == {
        "n": 1, "median": None, "max": None, "passes_15": False, "passes_30": False, "reason_15": FEWER, "reason_30": FEWER
    }  # fmt: skip
    assert am_row(con, "ZERO") == {
        "n": 0, "median": None, "max": None, "passes_15": False, "passes_30": False, "reason_15": FEWER, "reason_30": FEWER
    }  # fmt: skip


def test_periods_are_half_open_in_sql():
    # 06:00:00 is the first AM-peak second; 09:00:00 is midday; 15:00:00 PM peak; 18:00:00 evening; 22:00:00 nothing.
    f = Feeds()
    times = ["05:59:59", "06:00:00", "08:59:59", "09:00:00", "14:59:59", "15:00:00", "17:59:59", "18:00:00", "21:59:59"]
    f.trips(AFTER, "A", "weekday", 0, [at(t) for t in times + ["22:00:00", "25:10:00"]])
    con = f.build()
    counts = dict(
        con.execute(
            "select period, n_departures from route_period_headway where route_short_name = 'A' and date = ?",
            [WED_AFTER],
        ).fetchall()
    )
    assert counts == {"am_peak": 2, "midday": 2, "pm_peak": 2, "evening": 2}
    # the 09:00:00 departure counts for midday only
    assert one(
        con,
        "select count(*) from period_departures where period = 'am_peak' and departure_s = 32400",
    ) == (0,)


def test_first_stop_uses_the_integer_stop_sequence_not_the_text_order():
    # As text '10' < '2' < '9'. The first stop is sequence 2 (06:10:00); the last is sequence 10 (arrives 07:30:00).
    f = Feeds()
    stops = [
        ("9", at("07:00:00"), at("07:00:00")),
        ("10", at("07:30:00"), at("07:35:00")),
        ("2", at("06:10:00"), at("06:10:00")),
    ]
    f.trip(AFTER, "A", "weekday", 0, 0, stops=stops)
    con = f.build()
    assert one(con, "select departure_s, stop_sequence from first_stop_departures") == (at("06:10:00"), 2)
    assert one(con, "select arrival_s, stop_sequence from last_stop_arrivals") == (at("07:30:00"), 10)


@pytest.mark.parametrize(
    ("first", "last", "ok"),
    [
        ("05:00:00", "25:30:00", True),  # MTC-06 3.7: between 5:00 a.m. and 1:30 a.m.; both exactly on the boundary
        ("04:59:59", "25:30:00", True),
        ("05:00:01", "25:30:00", False),
        ("05:00:00", "25:29:59", False),
    ],
)
def test_span_boundary_in_sql(first, last, ok):
    f = Feeds()
    f.trip(AFTER, "A", "weekday", 0, at(first), last_arr=at("06:00:00"))
    f.trip(AFTER, "A", "weekday", 1, at("12:00:00"), last_arr=at(last))
    row = one(
        f.build(),
        "select span_start, span_end, span_applicable, span_pass from route_span where route_short_name = 'A'",
    )
    assert row == (first, last, True, ok)


def test_span_covers_both_directions():
    f = Feeds()
    # Neither direction passes alone: the start comes from direction 1, the end from direction 0.
    f.trip(AFTER, "A", "weekday", 0, at("05:30:00"), last_arr=at("26:00:00"))
    f.trip(AFTER, "A", "weekday", 1, at("04:55:00"), last_arr=at("12:00:00"))
    assert one(f.build(), "select span_start, span_end, span_pass from route_span") == ("04:55:00", "26:00:00", True)


def test_express_route_has_no_span_verdict_and_no_headway_verdict():
    f = Feeds()
    f.trips(AFTER, "9x", "weekday", 0, every(at("06:00:00"), at("07:00:00"), 900))
    con = f.build()
    assert one(con, "select span_applicable, span_pass from route_span") == (False, None)
    assert con.execute("select distinct passes_15, passes_30, reason_15 from route_period_headway").fetchall() == [
        (None, None, None)
    ]
    assert one(con, "select tier from route_compliance where date = ? and route_short_name = '9x'", WED_AFTER) == (
        "not scored (express)",
    )


def express_pass(f, route="9x", date=WED_AFTER):
    con = f.build()
    return con, one(
        con, "select express_pass from route_compliance where date = ? and route_short_name = ?", date, route
    )[0]


def test_express_needs_three_trips_in_the_peak_flow_direction_of_each_peak():
    # MTC-06 3.7: "a minimum of three trips in each peak direction". Exactly 3 passes, 2 fails.
    f = Feeds()
    f.trips(AFTER, "9x", "weekday", 0, [at("06:10:00"), at("07:10:00"), at("08:10:00")])
    f.trips(AFTER, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    assert express_pass(f)[1] is True
    g = Feeds()
    g.trips(AFTER, "9x", "weekday", 0, [at("06:10:00"), at("07:10:00")])  # 2 in the AM peak
    g.trips(AFTER, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    con, ok = express_pass(g)
    assert ok is False
    assert one(con, "select peak_flow_count, passes from express_peak_trips where period = 'am_peak'") == (2, False)


def test_express_other_direction_is_ignored_and_two_directions_are_not_added_together():
    # AM: 2 trips outbound + 2 inbound = 4 in total, but the peak-flow direction has only 2, so it fails.
    f = Feeds()
    f.trips(AFTER, "9x", "weekday", 0, [at("06:10:00"), at("07:10:00")])
    f.trips(AFTER, "9x", "weekday", 1, [at("06:20:00"), at("07:20:00")])
    f.trips(AFTER, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    con, ok = express_pass(f)
    assert ok is False
    assert one(con, "select peak_flow_count, peak_flow_direction from express_peak_trips where period = 'am_peak'") == (
        2,
        None,
    )  # a tie: the shared count, no direction
    # a thin opposite direction cannot fail the route (64x pattern)
    g = Feeds()
    g.trips(AFTER, "9x", "weekday", 0, [at("06:10:00"), at("07:10:00"), at("08:10:00"), at("15:10:00")])
    g.trips(AFTER, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    assert express_pass(g)[1] is True


def test_express_peak_boundaries_are_half_open():
    # A trip at 09:00:00 is not an AM-peak trip, and one at 06:00:00 is.
    f = Feeds()
    f.trips(AFTER, "9x", "weekday", 0, [at("06:00:00"), at("07:00:00"), at("09:00:00")])
    f.trips(AFTER, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    con, ok = express_pass(f)
    assert ok is False
    assert one(con, "select peak_flow_count from express_peak_trips where period = 'am_peak'") == (2,)


def test_express_has_no_peak_rows_on_weekends():
    f = Feeds()
    f.trips(AFTER, "9x", "saturday", 0, every(at("06:00:00"), at("07:00:00"), 600))
    con = f.build()
    assert one(con, "select count(*) from express_peak_trips") == (0,)
    assert one(
        con, "select tier, express_pass from route_compliance where date = '2026-10-17' and route_short_name = '9x'"
    ) == (
        "not scored (express)",
        None,
    )


def full_day(f, feed, route, step, day_type="weekday", direction=0):
    f.trips(feed, route, day_type, direction, every(at("06:00:00"), at("17:30:00"), step))


def test_tier_follows_the_15_30_below_order():
    f = Feeds()
    full_day(f, AFTER, "T15", 900)
    full_day(f, AFTER, "T30", 1800)
    full_day(f, AFTER, "TLO", 1801)
    f.trips(AFTER, "T15", "weekday", 0, [at("06:00:00")])  # one extra trip adds a 0 gap: median unchanged
    con = f.build()
    tiers = dict(
        con.execute("select route_short_name, tier from route_compliance where date = ?", [WED_AFTER]).fetchall()
    )
    assert tiers == {"T15": "15-min", "T30": "30-min", "TLO": "below standard"}


def test_one_failing_direction_or_period_fails_the_route():
    # Direction 0 is 15 minutes all day; direction 1 has a 20-minute AM peak. Both directions must pass.
    f = Feeds()
    full_day(f, AFTER, "R", 900, direction=0)
    f.trips(AFTER, "R", "weekday", 1, every(at("06:00:00"), at("08:40:00"), 1200))
    f.trips(AFTER, "R", "weekday", 1, every(at("09:00:00"), at("17:45:00"), 900))
    con = f.build()
    assert one(con, "select tier, fail_reason_15, fail_reason_30 from route_compliance where date = ?", WED_AFTER) == (
        "30-min",
        "headway above standard",
        None,
    )
    assert one(
        con,
        "select weakest_direction, weakest_period, weakest_median_s from route_compliance where date = ?",
        WED_AFTER,
    ) == (
        1,
        "am_peak",
        1200.0,
    )


def test_route_fail_reason_lists_both_reasons():
    f = Feeds()
    full_day(f, AFTER, "R", 2400, direction=0)  # real long headway
    f.trips(AFTER, "R", "weekday", 1, [at("12:00:00")])  # direction 1: one trip, no AM peak headway
    con = f.build()
    assert one(con, "select fail_reason_30 from route_compliance where date = ?", WED_AFTER) == (
        "fewer than 2 departures in period; headway above standard",
    )


def test_evening_and_midday_do_not_change_the_15_minute_tier():
    # 15 is scored in the AM and PM peaks only; a 40-minute midday fails 30 but not 15 (as the sheet's decision 3 reads).
    f = Feeds()
    f.trips(AFTER, "R", "weekday", 0, every(at("06:00:00"), at("08:45:00"), 900))
    f.trips(AFTER, "R", "weekday", 0, every(at("09:00:00"), at("14:40:00"), 2400))
    f.trips(AFTER, "R", "weekday", 0, every(at("15:00:00"), at("17:45:00"), 900))
    f.trips(AFTER, "R", "weekday", 0, [at("19:00:00"), at("21:00:00")])  # evening, no verdict
    con = f.build()
    assert one(con, "select tier, tier_15_pass, tier_30_pass from route_compliance where date = ?", WED_AFTER) == (
        "15-min",
        True,
        False,
    )
    assert one(
        con,
        "select passes_15, passes_30, reason_30 from route_period_headway where period = 'evening' and date = ?",
        WED_AFTER,
    ) == (None, None, None)


def test_weekend_is_report_only_and_no_service_is_reported():
    f = Feeds()
    f.trips(AFTER, "W", "saturday", 0, every(at("09:00:00"), at("12:00:00"), 3600))
    f.trips(AFTER, "W", "weekday", 0, [at("07:00:00")])  # service on Wednesday only for route V
    f.trips(AFTER, "V", "weekday", 0, [at("07:00:00")])
    con = f.build()
    rows = dict(
        con.execute(
            "select route_short_name || ' ' || cast(date as varchar), tier from route_compliance "
            "where feed_version = ?",
            [AFTER],
        ).fetchall()
    )
    assert rows["W 2026-10-17"] == "report only"
    assert rows["W 2026-10-18"] == "no service on date"
    assert rows["V 2026-10-17"] == "no service on date"
    assert one(
        con,
        "select passes_15, passes_30, covers_15, covers_30, n_departures, headway_median_s "
        "from route_period_headway where date = '2026-10-17' and route_short_name = 'W'",
    ) == (None, None, False, False, 4, 3600.0)


def test_weekend_day_period_is_half_open_09_to_18():
    f = Feeds()
    f.trips(AFTER, "W", "sunday", 0, [at(t) for t in ("08:59:59", "09:00:00", "17:59:59", "18:00:00")])
    assert one(f.build(), "select n_departures from route_period_headway where period = 'weekend_day'") == (2,)


def test_rail_routes_are_out_and_a_route_with_no_trips_still_gets_a_row():
    f = Feeds()
    f.trips(AFTER, "501", "weekday", 0, [at("06:00:00")], route_type="0")
    f.route(AFTER, "EMPTY")
    con = f.build()
    assert con.execute("select route_short_name, tier from route_compliance where date = '2026-10-14'").fetchall() == [
        ("EMPTY", "no service on date")
    ]


def test_service_removed_by_exception_type_2_is_not_active():
    f = Feeds()
    f.trip(AFTER, "A", "weekday", 0, at("07:00:00"))
    f.trip(AFTER, "B", "weekday", 0, at("07:00:00"))
    f.day(AFTER, "20261014", service="svc-20261014", exception="2")  # removes the service A and B both use
    f.day(AFTER, "20261014", service="svc-other", exception="1")
    con = f.build()
    assert one(con, "select count(*) from active_trips") == (0,)


def test_trips_outside_the_comparison_dates_are_not_counted():
    f = Feeds()
    f.trip(AFTER, "A", "weekday", 0, at("07:00:00"))  # Wed 2026-10-14: counted
    f.trip(AFTER, "A", "weekday", 0, at("08:00:00"), date="20261015")  # Thu 2026-10-15: not a comparison date
    con = f.build()
    assert one(con, "select count(*) from active_trips") == (1,)
    assert one(con, "select count(*) from comparison_dates") == (6,)


def test_before_after_change_values():
    f = Feeds()
    # UP: 30-min before, 15-min after. DOWN: 15-min before, below standard after. SAME. NEW. GONE.
    full_day(f, BEFORE, "UP", 1800)
    full_day(f, AFTER, "UP", 900)
    full_day(f, BEFORE, "DOWN", 900)
    full_day(f, AFTER, "DOWN", 2400)
    full_day(f, BEFORE, "SAME", 1800)
    full_day(f, AFTER, "SAME", 1500)  # 25 minutes: still 30-min
    f.route(BEFORE, "NEW")
    full_day(f, AFTER, "NEW", 900)
    full_day(f, BEFORE, "GONE", 900)
    f.route(AFTER, "GONE")
    f.route(BEFORE, "NONE")
    f.route(AFTER, "NONE")
    con = f.build()
    got = dict(con.execute("select route_short_name, change from before_after").fetchall())
    assert got == {"UP": "up", "DOWN": "down", "SAME": "same", "NEW": "new", "GONE": "gone", "NONE": "same"}
    assert one(con, "select tier_before, tier_after from before_after where route_short_name = 'NEW'") == (
        "no service on date",
        "15-min",
    )


def test_before_after_for_express_follows_the_express_verdict():
    f = Feeds()
    for feed, am in ((BEFORE, 3), (AFTER, 2)):
        f.trips(feed, "9x", "weekday", 0, [at("06:10:00") + 600 * i for i in range(am)])
        f.trips(feed, "9x", "weekday", 1, [at("16:00:00"), at("16:30:00"), at("17:00:00")])
    assert one(f.build(), "select change, express_pass_before, express_pass_after from before_after") == (
        "down",
        True,
        False,
    )


def test_before_after_headway_change_in_seconds():
    f = Feeds()
    f.trips(BEFORE, "R", "weekday", 0, every(at("06:00:00"), at("07:00:00"), 900))
    f.trips(AFTER, "R", "weekday", 0, [*every(at("06:00:00"), at("06:45:00"), 900), at("07:01:00")])
    row = one(
        f.build(),
        "select median_before_s, median_after_s, median_change_s, max_before_s, max_after_s, max_change_s, "
        "before_date, after_date from before_after_headway where period = 'am_peak'",
    )
    assert row[:6] == (900.0, 900.0, 0.0, 900, 960, 60)
    assert (str(row[6]), str(row[7])) == (WED_BEFORE, WED_AFTER)
