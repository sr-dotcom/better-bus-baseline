"""Second method: recompute route and direction figures with gtfs-kit and compare them with the marts.

Run: uv run python analysis/crosscheck.py   (writes analysis/crosscheck_report.md)

gtfs-kit reads the zips on its own, picks the trips for a date with its own calendar code, and measures a trip's start
and end from its own stop_times handling, so agreement is real evidence. It does not define every value the way the
marts do. analysis/crosscheck_report.md lists each difference and compares what is comparable; the marts are not changed
to fit gtfs-kit. See DIFFERENCES below.
"""

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import gtfs_kit as gk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.build import build_in_memory
from ingest.gtfs_time import parse_gtfs_time
from ingest.load_gtfs import FEEDS

REPORT = ROOT / "analysis/crosscheck_report.md"
AM_PEAK = ("06:00:00", "09:00:00")  # the window as asked: gtfs-kit counts both ends
TOLERANCE_MINUTES = 1e-9

DIFFERENCES = [
    (
        "Headway window ends",
        (
            "gtfs-kit keeps a trip start `s` when `headway_start_time <= s <= headway_end_time`, so a trip at exactly the "
            "end time counts. The marts are half-open, `start <= s < end`. The first AM-peak run below uses the window as "
            "asked, 06:00:00 to 09:00:00. Whole-second times make `<= 08:59:59` the same set as `< 09:00:00`, so every "
            "scored comparison also runs with the end set to one second earlier, which is the marts' window."
        ),
    ),
    (
        "Headway unit",
        (
            "gtfs-kit returns minutes as a float (`max_headway`); the marts hold seconds. The cross-check divides the mart "
            "seconds by 60 and accepts a difference under 1e-9 minutes."
        ),
    ),
    (
        "Which stop a trip is measured at",
        (
            "Both take the stop_times row with the lowest `stop_sequence` as the trip start and use its `departure_time`. "
            "gtfs-kit sorts `stop_sequence` as an integer; the marts cast it to an integer in staging."
        ),
    ),
    (
        "End time",
        (
            "gtfs-kit `end_time` is the `departure_time` of the last stop. The span mart uses the `arrival_time` of the "
            "last stop (`last_arrival_s`), which is what the sheet defines. The report compares gtfs-kit `end_time` with "
            "both the mart value and the last-stop departure; where the two differ, the gap is the dwell time at the "
            "last stop. The table above shows whether any trip does."
        ),
    ),
    (
        "Zero-length trips",
        (
            "gtfs-kit drops trips whose duration is 0 or less (`end_time - start_time`, last-stop departure minus "
            "first-stop departure) before it counts trips or measures start, end and headway. The marts keep every "
            "active trip. The report counts trips both ways."
        ),
    ),
    (
        "Which trips run on a date",
        (
            "gtfs-kit uses its own calendar code on `calendar_dates.txt`. The marts use the `service_id` rule in "
            "`sql/intermediate/40_active_trips.sql` (an exception_type 1 row and no exception_type 2 row). Both feeds "
            "hold type 1 rows only. The trip-count rows in the table above show whether the two pick the same trips."
        ),
    ),
    (
        "Direction split",
        (
            "gtfs-kit `split_directions=True` groups by `direction_id`. Route start and end in `route_span` cover both "
            "directions, so the route-level check takes the earliest start and the latest end over the two gtfs-kit "
            "directions."
        ),
    ),
]


@dataclass
class Result:
    compared: dict = field(default_factory=dict)
    mismatches: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def count(self, check):
        self.compared[check] = self.compared.get(check, 0) + 1

    def miss(self, check, **kw):
        self.mismatches.append({"check": check, **kw})


def hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def mart_trip_table(con):
    """Per active trip: first departure, last departure and last arrival in seconds, from the staging view."""
    return con.execute(
        """
        select a.feed_version, a.date, a.route_short_name, a.direction_id, a.trip_id,
               arg_min(s.departure_s, s.stop_sequence) as first_dep,
               arg_max(s.departure_s, s.stop_sequence) as last_dep,
               arg_max(s.arrival_s, s.stop_sequence) as last_arr
        from active_trips a
        join stg_stop_times s on s.feed_version = a.feed_version and s.trip_id = a.trip_id
        group by all
        """
    ).fetchall()


def gtfs_kit_frames(zip_path: Path, dates: list[str], windows: dict):
    """gtfs-kit trip stats once for the dates, then route stats (split by direction) for each window."""
    feed = gk.read_feed(zip_path, dist_units="km")
    feed.shapes = None  # distances are not compared; this skips a slow shape calculation
    feed = feed.restrict_to_dates(dates)
    trip_stats = feed.compute_trip_stats()
    return {
        name: feed.compute_route_stats(dates, trip_stats, start, end, split_directions=True)
        for name, (start, end) in windows.items()
    }


def run(con=None) -> Result:
    con = con or build_in_memory()
    res = Result()
    bus = {r[0] for r in con.execute("select distinct route_short_name from bus_routes").fetchall()}
    periods = con.execute("select distinct period, start_s, end_s from periods order by 2, 1").fetchall()
    period_day_types = {}
    for period, day in con.execute("select period, day_type from periods").fetchall():
        period_day_types.setdefault(period, set()).add(day)

    # per (feed, date, route, direction) figures from the mart side
    trips = {}
    for feed_version, date, route, direction, trip_id, first_dep, last_dep, last_arr in mart_trip_table(con):
        trips.setdefault((feed_version, date.strftime("%Y%m%d"), route, direction), []).append(
            (trip_id, first_dep, last_dep, last_arr)
        )
    mart_headway = {
        (r[0], r[1].strftime("%Y%m%d"), r[2], r[3], r[4]): r[5]
        for r in con.execute(
            "select feed_version, date, route_short_name, direction_id, period, headway_max_s from route_period_headway"
        ).fetchall()
    }
    route_span = {
        (r[0], r[1].strftime("%Y%m%d"), r[2]): (r[3], r[4], r[5])
        for r in con.execute(
            "select feed_version, date, route_short_name, first_departure_s, last_arrival_s, n_trips from route_span"
        ).fetchall()
    }
    dates_by_feed = {}
    for feed_version, date in con.execute("select feed_version, date from comparison_dates").fetchall():
        dates_by_feed.setdefault(feed_version, []).append(date.strftime("%Y%m%d"))
    day_type = {
        (r[0], r[1].strftime("%Y%m%d")): r[2]
        for r in con.execute("select feed_version, date, day_type from comparison_dates").fetchall()
    }

    for feed_version, zip_path in FEEDS.items():
        dates = sorted(dates_by_feed[feed_version])
        windows = {"am_peak_as_asked": AM_PEAK}
        for period, start_s, end_s in periods:
            windows[period] = (hms(start_s), hms(end_s - 1))  # half-open end as the last whole second
        frames = gtfs_kit_frames(zip_path, dates, windows)

        # trip count, start and end: any window gives the same values, so read them from the first frame
        base = frames["am_peak_as_asked"]
        base = base[base["route_short_name"].isin(bus)]
        seen = set()
        for row in base.itertuples():
            key = (feed_version, row.date, row.route_short_name, int(row.direction_id))
            seen.add(key)
            mine = trips.get(key, [])
            tag = {"feed": feed_version, "date": row.date, "route": row.route_short_name, "direction": key[3]}
            positive = [t for t in mine if t[2] > t[1]]  # gtfs-kit keeps only trips longer than 0 seconds

            res.count("trip count, all active trips")
            if row.num_trips != len(mine):
                res.miss("trip count, all active trips", **tag, mart=len(mine), gtfs_kit=int(row.num_trips))
            res.count("trip count, trips longer than 0 s")
            if row.num_trips != len(positive):
                res.miss("trip count, trips longer than 0 s", **tag, mart=len(positive), gtfs_kit=int(row.num_trips))

            res.count("start time (earliest first-stop departure)")
            g_start = parse_gtfs_time(row.start_time)
            m_start = min(t[1] for t in mine) if mine else None
            if g_start != m_start:
                res.miss("start time (earliest first-stop departure)", **tag, mart=m_start, gtfs_kit=g_start)

            res.count("end time vs mart last-stop arrival")
            g_end = parse_gtfs_time(row.end_time)
            m_end_arr = max(t[3] for t in mine) if mine else None
            if g_end != m_end_arr:
                res.miss("end time vs mart last-stop arrival", **tag, mart=m_end_arr, gtfs_kit=g_end)

            res.count("end time vs last-stop departure")
            m_end_dep = max(t[2] for t in mine) if mine else None
            if g_end != m_end_dep:
                res.miss("end time vs last-stop departure", **tag, mart=m_end_dep, gtfs_kit=g_end)

        # route level span: earliest start and latest end over both gtfs-kit directions against route_span
        by_route = {}
        for row in base.itertuples():
            k = (feed_version, row.date, row.route_short_name)
            s, e = parse_gtfs_time(row.start_time), parse_gtfs_time(row.end_time)
            cur = by_route.get(k)
            by_route[k] = (s, e) if cur is None else (min(cur[0], s), max(cur[1], e))
        for k, (s, e) in by_route.items():
            tag = {"feed": k[0], "date": k[1], "route": k[2], "direction": "both"}
            res.count("route span start")
            if route_span.get(k, (None,))[0] != s:
                res.miss("route span start", **tag, mart=route_span.get(k, (None,))[0], gtfs_kit=s)
            res.count("route span end vs mart last_arrival_s")
            if route_span.get(k, (None, None))[1] != e:
                res.miss(
                    "route span end vs mart last_arrival_s", **tag, mart=route_span.get(k, (None, None))[1], gtfs_kit=e
                )

        # keys the mart has but gtfs-kit does not return (for example a direction with only zero-length trips)
        only_mart = sorted(k for k in trips if k[0] == feed_version and k not in seen)
        for key in only_mart:
            res.miss(
                "route-direction present in both",
                feed=key[0],
                date=key[1],
                route=key[2],
                direction=key[3],
                mart=len(trips[key]),
                gtfs_kit=0,
            )
        res.compared["route-direction present in both"] = (
            res.compared.get("route-direction present in both", 0) + len(seen) + len(only_mart)
        )

        # max headway per period window (half-open emulation), plus the as-asked inclusive AM window
        for name, frame in frames.items():
            frame = frame[frame["route_short_name"].isin(bus)]
            by_key = {(r.date, r.route_short_name, int(r.direction_id)): r.max_headway for r in frame.itertuples()}
            check = "AM-peak max headway, window as asked 06:00:00-09:00:00 (both ends counted)"
            if name == "am_peak_as_asked":
                period = "am_peak"
            else:
                period = name
                check = f"max headway, {name} window (half-open)"
            for (fv, date, route, direction, p), mart_max in mart_headway.items():
                if fv != feed_version or p != period or day_type[(fv, date)] not in period_day_types[period]:
                    continue
                gk_max = by_key.get((date, route, direction))
                res.count(check)
                mart_min = None if mart_max is None else mart_max / 60
                same = (mart_min is None and (gk_max is None or math.isnan(gk_max))) or (
                    mart_min is not None and gk_max is not None and abs(mart_min - gk_max) < TOLERANCE_MINUTES
                )
                if not same:
                    res.miss(
                        check, feed=fv, date=date, route=route, direction=direction, mart=mart_min, gtfs_kit=gk_max
                    )
    classify_inclusive_window(con, res)
    return res


def classify_inclusive_window(con, res: Result) -> None:
    """Every as-asked AM mismatch should be a route-direction with a trip at exactly 09:00:00."""
    at_nine = {
        (r[0], r[1].strftime("%Y%m%d"), r[2], r[3])
        for r in con.execute(
            "select feed_version, date, route_short_name, direction_id from first_stop_departures "
            "where departure_s = 32400"
        ).fetchall()
    }
    for m in res.mismatches:
        if m["check"].startswith("AM-peak max headway, window as asked"):
            m["explained"] = (m["feed"], m["date"], m["route"], m["direction"]) in at_nine


def write_report(res: Result, path: Path = REPORT) -> None:
    lines = ["# gtfs-kit cross-check", ""]
    lines += [
        (
            "Second method for the marts: gtfs-kit recomputes each route and direction from the raw zips, and "
            "`analysis/crosscheck.py` compares it with the marts. Generated by that script; do not edit by hand."
        ),
        "",
        (
            f"gtfs-kit {gk.__version__}, `split_directions=True`, bus routes only, the six comparison dates "
            "(each date from its own feed)."
        ),
        "",
        "## What was compared",
        "",
        "| check | values compared | mismatches |",
        "| --- | --- | --- |",
    ]
    for check, n in res.compared.items():
        bad = sum(1 for m in res.mismatches if m["check"] == check)
        lines.append(f"| {check} | {n} | {bad} |")
    lines += ["", "## How gtfs-kit defines a value differently", ""]
    for title, text in DIFFERENCES:
        lines += [f"- **{title}.** {text}"]
    lines += ["", "## Mismatches", ""]
    if not res.mismatches:
        lines.append("None.")
    for check in dict.fromkeys(m["check"] for m in res.mismatches):
        rows = [m for m in res.mismatches if m["check"] == check]
        lines += [
            f"### {check}: {len(rows)}",
            "",
            "| feed | date | route | direction | mart | gtfs-kit | note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for m in rows:
            note = ""
            if "explained" in m:
                note = "trip at exactly 09:00:00" if m["explained"] else "NOT EXPLAINED"
            lines.append(
                f"| {m['feed']} | {m['date']} | {m['route']} | {m['direction']} | {m['mart']} | {m['gtfs_kit']} | {note} |"
            )
        lines.append("")
    for note in res.notes:
        lines += [note, ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    con = build_in_memory()
    res = run(con)
    write_report(res)
    total = sum(res.compared.values())
    print(f"compared {total} values, {len(res.mismatches)} mismatches; wrote {REPORT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
