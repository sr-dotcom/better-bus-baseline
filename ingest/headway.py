"""Headway statistics for one route and direction, from first-stop departure times in seconds.

Pure functions so the L3 marts and the gtfs-kit cross-check can share one definition. Method: docs/metrics.md.
"""

import itertools
import statistics

# Periods are an analysis choice: MTC-06 defines no peak hours (see data/reference/mtc06.md). Seconds since service-day start.
# Half-open: a departure belongs to a period if start <= departure < end, so 09:00:00 is midday, not AM peak.
PERIODS = {
    "am_peak": (6 * 3600, 9 * 3600),
    "midday": (9 * 3600, 15 * 3600),
    "pm_peak": (15 * 3600, 18 * 3600),
    "evening": (18 * 3600, 22 * 3600),
    "weekend_day": (9 * 3600, 18 * 3600),
}

# MTC-06 3.7: "at least 15-minute peak service" and "at least 30-minute service". A gap of exactly 15:00 passes.
LIMIT_15_SECONDS = 15 * 60
LIMIT_30_SECONDS = 30 * 60


def departures_in_period(departures: list[int], period: str) -> list[int]:
    start, end = PERIODS[period]
    return sorted(d for d in departures if start <= d < end)


def headway_stats(departures: list[int]) -> dict | None:
    """Median and max gap (seconds) between consecutive departures. None when fewer than 2 departures.

    The median of an even number of gaps is the mean of the two middle gaps.
    """
    deps = sorted(departures)
    if len(deps) < 2:
        return None
    gaps = [b - a for a, b in itertools.pairwise(deps)]
    return {"median": statistics.median(gaps), "max": max(gaps), "gaps": gaps}


def meets_standard(stats: dict | None, limit_seconds: int) -> bool:
    """Pass uses the median. No headway (fewer than 2 departures) fails."""
    return stats is not None and stats["median"] <= limit_seconds


# MTC-06 3.7: "CATS Fixed Route Services will operate between 5:00 a.m. and 1:30 a.m." Seconds since service-day start.
SPAN_START_LATEST = 5 * 3600
SPAN_END_EARLIEST = 25 * 3600 + 30 * 60

# MTC-06 3.7: "Express and Regional Express services will have a minimum of three trips in each peak direction."
EXPRESS_MIN_PEAK_TRIPS = 3


def span_meets_standard(start: int, end: int) -> bool:
    """Start at or before 05:00:00 and end at or after 25:30:00 (01:30 the next morning)."""
    return start <= SPAN_START_LATEST and end >= SPAN_END_EARLIEST


def express_peak_meets_standard(trips: int) -> bool:
    return trips >= EXPRESS_MIN_PEAK_TRIPS
