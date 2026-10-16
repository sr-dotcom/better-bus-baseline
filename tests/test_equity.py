"""Area weighting and stop buffers (analysis/equity.py) on hand-made squares in a metre CRS. No downloads."""

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from analysis.equity import BUFFER_M, CRS_M, stop_buffers, weighted_population


def tracts(*specs):
    """specs: (geometry, population). A GeoDataFrame in the metre CRS."""
    return gpd.GeoDataFrame({"pop": [p for _, p in specs]}, geometry=[g for g, _ in specs], crs=CRS_M)


def test_half_the_tract_inside_the_buffer_gives_half_the_population():
    # Hand calculation: tract 1000 m x 1000 m with 1000 residents; the buffer covers its left 500 m
    # (area 500 000 of 1 000 000 m2), so 1000 x 0.5 = 500 residents.
    residents, touched, missing = weighted_population(box(0, 0, 500, 1000), tracts((box(0, 0, 1000, 1000), 1000)))
    assert residents == pytest.approx(500.0)
    assert (touched, missing) == (1, 0)


def test_buffer_covering_the_whole_tract_gives_all_residents():
    # Boundary: the buffer is exactly the tract, share = 1.
    residents, touched, _ = weighted_population(box(0, 0, 1000, 1000), tracts((box(0, 0, 1000, 1000), 1000)))
    assert residents == pytest.approx(1000.0)
    assert touched == 1


def test_a_tract_that_only_shares_an_edge_is_not_touched():
    # Boundary: the buffer ends exactly where the tract starts, overlap area 0, so no residents and no tract counted.
    residents, touched, _ = weighted_population(box(-500, 0, 0, 1000), tracts((box(0, 0, 1000, 1000), 1000)))
    assert residents == 0.0
    assert touched == 0


def test_two_tracts_are_summed_by_their_own_shares():
    # Left tract (500 residents) is fully inside; right tract (2000 residents, 1000 m wide) has 250 m inside = 0.25.
    # 500 x 1 + 2000 x 0.25 = 1000.
    two = tracts((box(0, 0, 1000, 1000), 500), (box(1000, 0, 2000, 1000), 2000))
    residents, touched, _ = weighted_population(box(0, 0, 1250, 1000), two)
    assert residents == pytest.approx(1000.0)
    assert touched == 2


def test_a_tract_without_an_estimate_adds_nothing_and_is_counted():
    # No value is filled in: the tract is reported as touched and as missing, and adds 0.
    nan_tract = tracts((box(0, 0, 1000, 1000), float("nan")))
    residents, touched, missing = weighted_population(box(0, 0, 500, 1000), nan_tract)
    assert (residents, touched, missing) == (0.0, 1, 1)


def test_buffers_of_two_close_stops_are_dissolved_so_overlap_counts_once():
    # Two stops 100 m apart: the dissolved area is less than two full discs, and a tract that holds both discs is
    # counted once with its population x share, not twice.
    points = gpd.GeoDataFrame(geometry=[Point(0, 0), Point(100, 0)], crs=CRS_M)
    merged = stop_buffers(points)
    single = Point(0, 0).buffer(BUFFER_M).area
    assert single < merged.area < 2 * single
    big = tracts((box(-5000, -5000, 5000, 5000), 100_000))
    residents, touched, _ = weighted_population(merged, big)
    assert residents == pytest.approx(100_000 * merged.area / (10_000 * 10_000))
    assert touched == 1


def test_buffer_reaches_a_tract_at_799_m_but_not_at_801_m():
    # Boundary on the distance: the tract starts 799 m or 801 m east of the stop; the buffer radius is 800 m.
    stop = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs=CRS_M)
    buffer_geom = stop_buffers(stop)
    near = tracts((box(799, -50, 1800, 50), 100))
    far = tracts((box(801, -50, 1800, 50), 100))
    assert weighted_population(buffer_geom, near)[1] == 1
    assert weighted_population(buffer_geom, far)[1] == 0
