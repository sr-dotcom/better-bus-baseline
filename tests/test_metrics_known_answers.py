"""Known-answer and boundary tests for the metric helpers (docs/metrics.md, docs/known-answers.md).

Live tests run on synthetic or hand-copied departure seconds. Tests marked skip compare the L3 marts with the numbers
in docs/known-answers.md and switch on when the marts exist.
"""

import pytest

from ingest.gtfs_time import parse_gtfs_time
from ingest.headway import (
    HEADWAY_ABOVE_STANDARD,
    LIMIT_15_SECONDS,
    LIMIT_30_SECONDS,
    NO_SERVICE_IN_PERIOD,
    departures_in_period,
    express_meets_standard,
    express_peak_meets_standard,
    headway_stats,
    meets_standard,
    peak_flow_count,
    period_fail_reason,
    route_fail_reason,
    span_meets_standard,
)

MIN = 60


def at(minutes_gaps, start=6 * 3600):
    """Departure seconds from a start and a list of gaps in seconds."""
    out = [start]
    for g in minutes_gaps:
        out.append(out[-1] + g)
    return out


# ---- headway_median, tier_15: MTC-06 3.7 "at least 15-minute peak service on high frequency routes"


def test_gaps_of_exactly_15_minutes_pass_15():
    # MTC-06 3.7: 15-minute service means a 15:00 headway meets the standard, so exactly 900 s passes.
    stats = headway_stats(at([900] * 6))
    assert stats["median"] == 900
    assert meets_standard(stats, LIMIT_15_SECONDS)


def test_median_one_second_over_15_fails():
    # Hand calculation: gaps 900 and 901 -> two gaps, median = (900 + 901) / 2 = 900.5 > 900, so it fails.
    # Two gaps (even count) make the median move; with three or more gaps one long gap would not.
    stats = headway_stats(at([900, 901]))
    assert stats["median"] == 900.5
    assert not meets_standard(stats, LIMIT_15_SECONDS)


def test_one_long_gap_does_not_move_an_odd_median():
    # Pass/fail uses the median, not the max: gaps 900, 900, 901 -> median 900 passes while max is 901 (headway_max).
    stats = headway_stats(at([900, 900, 901]))
    assert stats["median"] == 900
    assert stats["max"] == 901
    assert meets_standard(stats, LIMIT_15_SECONDS)


def test_even_median_is_mean_of_two_middle_gaps():
    # Hand calculation: sorted gaps 600, 900, 1200, 1500 -> middle two 900 and 1200 -> median 1050.
    stats = headway_stats(at([1500, 600, 1200, 900]))
    assert stats["median"] == 1050


def test_single_departure_has_no_headway():
    # A direction with one in-period trip has no gap to measure; it fails the period (decision recorded in metrics.md).
    assert headway_stats([6 * 3600]) is None
    assert headway_stats([]) is None
    assert not meets_standard(None, LIMIT_30_SECONDS)


def test_unsorted_input_is_sorted_first():
    assert headway_stats([3000, 0, 1500])["gaps"] == [1500, 1500]


# ---- tier_30: MTC-06 3.7 "at least 30-minute service on Common/local routes"


def test_gaps_of_exactly_30_minutes_pass_30_and_fail_15():
    stats = headway_stats(at([1800] * 4))
    assert meets_standard(stats, LIMIT_30_SECONDS)
    assert not meets_standard(stats, LIMIT_15_SECONDS)


def test_30_minutes_plus_one_second_fails_30():
    stats = headway_stats(at([1800, 1801]))
    assert not meets_standard(stats, LIMIT_30_SECONDS)


# ---- periods (analysis choice, no MTC-06 definition): half-open start <= departure < end


def test_period_boundaries_are_half_open():
    nine = 9 * 3600
    assert departures_in_period([nine - 1, nine], "am_peak") == [nine - 1]  # 08:59:59 is AM peak, 09:00:00 is not
    assert departures_in_period([nine - 1, nine], "midday") == [nine]
    assert departures_in_period([6 * 3600 - 1, 6 * 3600], "am_peak") == [6 * 3600]  # 06:00:00 is the first AM second
    assert departures_in_period([15 * 3600], "midday") == []
    assert departures_in_period([15 * 3600], "pm_peak") == [15 * 3600]


def test_departure_after_midnight_is_not_in_a_day_period():
    # GTFS times past 24:00:00 are still seconds since service-day start; none of the day periods hold them.
    late = parse_gtfs_time("25:10:00")
    assert all(departures_in_period([late], p) == [] for p in ("am_peak", "midday", "pm_peak", "evening"))


# ---- span_pass: MTC-06 3.7 "between 5:00 a.m. and 1:30 a.m."


@pytest.mark.parametrize(
    ("start", "end", "ok"),
    [
        ("05:00:00", "25:30:00", True),  # both exactly on the boundary
        ("04:59:59", "25:30:00", True),
        ("05:00:01", "25:30:00", False),  # starts one second late
        ("05:00:00", "25:29:59", False),  # ends one second early
        ("04:50:00", "25:52:00", True),  # Route 9, Wed 2026-10-14 (docs/known-answers.md)
        ("05:42:00", "25:44:00", False),  # Route 39, Wed 2026-10-14
    ],
)
def test_span_boundaries(start, end, ok):
    assert span_meets_standard(parse_gtfs_time(start), parse_gtfs_time(end)) is ok


# ---- fail_reason on the tier metrics: "no service in period" (fewer than 2 departures) vs "headway above standard"


def test_fail_reason_no_service_in_period_for_zero_or_one_departure():
    # Decision: fewer than 2 in-period departures means no headway; the period fails with its own reason.
    assert period_fail_reason(headway_stats([]), LIMIT_30_SECONDS) == NO_SERVICE_IN_PERIOD
    assert period_fail_reason(headway_stats([7 * 3600]), LIMIT_30_SECONDS) == NO_SERVICE_IN_PERIOD
    assert NO_SERVICE_IN_PERIOD == "no service in period"


def test_fail_reason_headway_above_standard_for_a_real_long_median():
    # MTC-06 3.7: 31:00 service is below "at least 30-minute service"; this is a real median, not missing service.
    assert period_fail_reason(headway_stats(at([1860, 1860])), LIMIT_30_SECONDS) == HEADWAY_ABOVE_STANDARD
    assert period_fail_reason(headway_stats(at([1801, 1801])), LIMIT_30_SECONDS) == HEADWAY_ABOVE_STANDARD
    assert HEADWAY_ABOVE_STANDARD == "headway above standard"


def test_fail_reason_is_none_on_the_boundary_and_below():
    assert period_fail_reason(headway_stats(at([900, 900])), LIMIT_15_SECONDS) is None
    assert period_fail_reason(headway_stats(at([1800, 1800])), LIMIT_30_SECONDS) is None
    # the same 30:00 median fails the 15-minute standard with the headway reason, not the no-service reason
    assert period_fail_reason(headway_stats(at([1800, 1800])), LIMIT_15_SECONDS) == HEADWAY_ABOVE_STANDARD


def test_route_fail_reason_collects_distinct_reasons():
    assert route_fail_reason([None, None]) is None
    assert route_fail_reason([None, NO_SERVICE_IN_PERIOD, NO_SERVICE_IN_PERIOD]) == NO_SERVICE_IN_PERIOD
    assert route_fail_reason([HEADWAY_ABOVE_STANDARD, None]) == HEADWAY_ABOVE_STANDARD
    assert route_fail_reason([NO_SERVICE_IN_PERIOD, HEADWAY_ABOVE_STANDARD]) == (
        f"{HEADWAY_ABOVE_STANDARD}; {NO_SERVICE_IN_PERIOD}"
    )


# ---- express_peak_trips: MTC-06 3.7 "a minimum of three trips in each peak direction"
# Decision: count the peak-flow direction only, the direction with more trips in that peak, AM and PM separately.


def test_express_peak_boundary():
    assert express_peak_meets_standard(3)
    assert not express_peak_meets_standard(2)


def test_peak_flow_direction_is_the_one_with_more_trips():
    assert peak_flow_count([6, 0]) == 6
    assert peak_flow_count([0, 7]) == 7
    assert peak_flow_count([2, 1]) == 2


def test_peak_flow_tie_gives_the_shared_count():
    # Equal counts in both directions: either direction is the peak flow and the count is the same.
    assert peak_flow_count([3, 3]) == 3
    assert express_meets_standard([3, 3], [3, 3])
    assert not express_meets_standard([2, 2], [3, 3])


def test_express_boundary_in_the_peak_flow_direction():
    assert express_meets_standard([3, 0], [0, 3])  # exactly 3 in each peak-flow direction passes
    assert not express_meets_standard([2, 0], [0, 3])  # 2 in the AM peak fails
    assert not express_meets_standard([3, 0], [0, 2])  # 2 in the PM peak fails


def test_express_off_peak_direction_is_ignored():
    # MTC-06 3.7: "each peak direction" is read as the peak-flow direction, so a thin opposite direction cannot fail it.
    assert express_meets_standard([6, 0], [1, 7])  # 64x: AM flow direction 0, PM flow direction 1
    assert express_meets_standard([3, 0], [0, 3]) == express_meets_standard([3, 2], [2, 3])
    assert not express_meets_standard([2, 1], [0, 3])  # 40x: the AM flow direction has only 2 trips


# ---- known answers on real rows, hand-copied from docs/known-answers.md (Route 9, direction 0, AM peak)

ROUTE9_AFTER = ["06:05:00", "06:20:00", "06:35:00", "06:50:00", "07:05:00", "07:20:00",
                "07:36:00", "07:51:00", "08:06:00", "08:21:00", "08:36:00", "08:51:00"]  # fmt: skip
ROUTE9_BEFORE = ["06:05:00", "06:20:00", "06:35:00", "06:50:00", "07:05:00", "07:20:00",
                 "07:35:00", "07:50:00", "08:05:00", "08:20:00", "08:35:00", "08:50:00"]  # fmt: skip
ROUTE39_AFTER = ["06:15:00", "06:53:00", "07:28:00", "08:10:00", "08:53:00"]


def secs(times):
    return [parse_gtfs_time(t) for t in times]


def test_route9_after_known_answer():
    # Hand calculation from 12 first-stop rows: eleven gaps, ten of 15:00 and one of 16:00 (07:20:00 -> 07:36:00).
    stats = headway_stats(departures_in_period(secs(ROUTE9_AFTER), "am_peak"))
    assert len(stats["gaps"]) == 11
    assert stats["median"] == 15 * MIN
    assert stats["max"] == 16 * MIN
    assert meets_standard(stats, LIMIT_15_SECONDS)


def test_route9_before_known_answer():
    stats = headway_stats(departures_in_period(secs(ROUTE9_BEFORE), "am_peak"))
    assert (stats["median"], stats["max"]) == (15 * MIN, 15 * MIN)


def test_route39_after_known_answer_fails_30():
    # Gaps 38, 35, 42, 43 minutes -> sorted 35, 38, 42, 43 -> median (38 + 42) / 2 = 40:00 > 30:00.
    stats = headway_stats(departures_in_period(secs(ROUTE39_AFTER), "am_peak"))
    assert stats["gaps"] == [38 * MIN, 35 * MIN, 42 * MIN, 43 * MIN]
    assert stats["median"] == 40 * MIN
    assert not meets_standard(stats, LIMIT_30_SECONDS)


def test_express_known_answers_64x_and_40x():
    # Hand counts of first-stop departures from docs/known-answers.md section 4, Wed 2026-10-14, [direction 0, direction 1].
    assert express_meets_standard([6, 0], [1, 7])  # 64x: AM flow 6, PM flow 7 -> pass
    assert not express_meets_standard([2, 1], [0, 3])  # 40x: AM flow 2 -> fail; PM flow 3 would pass


# ---- mart checks: expected values from docs/known-answers.md, switched on in L3


def mart(metric, **keys):
    raise NotImplementedError("marts land in L3")


MARTS_LAND_IN_L3 = pytest.mark.skip(reason="marts land in L3")


@MARTS_LAND_IN_L3
@pytest.mark.parametrize(
    ("feed", "date", "route", "median", "maximum", "tier_15"),
    [
        ("2026-09-29", "2026-10-14", "9", 900, 960, True),
        ("2026-09-10", "2026-09-30", "9", 900, 900, True),
        ("2026-09-29", "2026-10-14", "39", 2400, 2580, False),
    ],
)
def test_mart_headway_am_peak_direction_0(feed, date, route, median, maximum, tier_15):
    row = mart("headway", feed=feed, date=date, route=route, direction="0", period="am_peak")
    assert (row["headway_median"], row["headway_max"], row["tier_15"]) == (median, maximum, tier_15)


@MARTS_LAND_IN_L3
def test_mart_route39_tier_is_below_standard():
    # Route 39 fails 15 and 30 in both directions on Wed 2026-10-14 AM peak (medians 40:00 and 39:30).
    assert mart("tier", feed="2026-09-29", date="2026-10-14", route="39")["tier"] == "below standard"


@MARTS_LAND_IN_L3
@pytest.mark.parametrize(
    ("feed", "date", "route", "start", "end", "span_pass"),
    [
        ("2026-09-29", "2026-10-14", "9", "04:50:00", "25:52:00", True),
        ("2026-09-10", "2026-09-30", "9", "04:50:00", "26:01:00", True),
        ("2026-09-29", "2026-10-14", "39", "05:42:00", "25:44:00", False),
        ("2026-09-10", "2026-09-30", "39", "05:42:00", "25:44:00", False),
    ],
)
def test_mart_span(feed, date, route, start, end, span_pass):
    row = mart("span", feed=feed, date=date, route=route)
    assert (row["span_start"], row["span_end"], row["span_pass"]) == (start, end, span_pass)


@MARTS_LAND_IN_L3
@pytest.mark.parametrize(
    ("route", "am_flow", "pm_flow", "express_pass"),
    [("64x", 6, 7, True), ("40x", 2, 3, False)],  # docs/known-answers.md section 4, Wed 2026-10-14
)
def test_mart_express_peak_flow_counts(route, am_flow, pm_flow, express_pass):
    row = mart("express_peak_trips", feed="2026-09-29", date="2026-10-14", route=route)
    assert (row["am_peak_flow_count"], row["pm_peak_flow_count"], row["express_pass"]) == (
        am_flow,
        pm_flow,
        express_pass,
    )


@MARTS_LAND_IN_L3
@pytest.mark.parametrize(
    ("route", "direction", "reason"),
    [("35", "0", NO_SERVICE_IN_PERIOD), ("28", "0", NO_SERVICE_IN_PERIOD), ("39", "0", HEADWAY_ABOVE_STANDARD)],
)
def test_mart_tier_fail_reason_am_peak(route, direction, reason):
    # docs/known-answers.md section 6: route 35 has 0 AM-peak departures, route 28 has 1, route 39 has a 40:00 median.
    row = mart("tier", feed="2026-09-29", date="2026-10-14", route=route, direction=direction, period="am_peak")
    assert (row["tier_15_fail_reason"], row["tier_30_fail_reason"]) == (reason, reason)


@MARTS_LAND_IN_L3
@pytest.mark.parametrize(("date", "has_service"), [("2026-10-14", True), ("2026-10-17", False), ("2026-10-18", False)])
def test_mart_no_service_on_date_route_50(date, has_service):
    row = mart("service", feed="2026-09-29", date=date, route="50")
    assert row["no_service_on_date"] is (not has_service)


@MARTS_LAND_IN_L3
def test_mart_before_after_change_route_9():
    # Median unchanged at 15:00, max gap 15:00 -> 16:00 (docs/known-answers.md section 1).
    row = mart("before_after", before="2026-09-30", after="2026-10-14", route="9", direction="0", period="am_peak")
    assert (row["median_change_seconds"], row["max_change_seconds"]) == (0, 60)
