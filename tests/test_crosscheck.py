"""The marts against gtfs-kit (analysis/crosscheck.py). Takes about a minute: gtfs-kit computes trip statistics itself."""

import pytest

from analysis.crosscheck import run

SPAN_CHECKS = (
    "start time (earliest first-stop departure)",
    "end time vs mart last-stop arrival",
    "route span start",
    "route span end vs mart last_arrival_s",
)
AM_AS_ASKED = "AM-peak max headway, window as asked 06:00:00-09:00:00 (both ends counted)"


@pytest.fixture(scope="module")
def result():
    return run()


def bad(result, check):
    return [m for m in result.mismatches if m["check"] == check]


@pytest.mark.parametrize("check", SPAN_CHECKS)
def test_span_columns_agree_with_gtfs_kit(result, check):
    assert result.compared[check] > 250
    assert bad(result, check) == []


def test_am_peak_max_headway_agrees_with_gtfs_kit_on_the_same_half_open_window(result):
    # gtfs-kit counts a trip at the window end, so the marts' half-open 06:00:00 <= t < 09:00:00 is gtfs-kit with the
    # end at 08:59:59. All other periods agree the same way.
    for check in (c for c in result.compared if c.startswith("max headway,")):
        assert result.compared[check] > 200, check
        assert bad(result, check) == [], check
    assert result.compared["max headway, am_peak window (half-open)"] == 246


def test_inclusive_window_differs_only_where_a_trip_leaves_at_exactly_09_00(result):
    # With 06:00:00-09:00:00 as asked, gtfs-kit includes a 09:00:00 departure and the marts do not. Each mismatch
    # must be a route and direction that has such a trip.
    rows = bad(result, AM_AS_ASKED)
    assert result.compared[AM_AS_ASKED] == 246
    assert all(m["explained"] for m in rows)


def test_trip_counts_and_route_directions_agree(result):
    assert bad(result, "trip count, all active trips") == []
    assert bad(result, "trip count, trips longer than 0 s") == []
    assert bad(result, "route-direction present in both") == []
    assert result.compared["trip count, all active trips"] == 578
