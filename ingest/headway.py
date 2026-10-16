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


# Why a scored period failed. "No service in period" means fewer than 2 departures, so there is no headway to compare
# (zero or one trip in the window); "headway above standard" means a real median above the limit.
NO_SERVICE_IN_PERIOD = "no service in period"
HEADWAY_ABOVE_STANDARD = "headway above standard"


def period_fail_reason(stats: dict | None, limit_seconds: int) -> str | None:
    """None when the period passes, else the reason it failed."""
    if stats is None:
        return NO_SERVICE_IN_PERIOD
    if not meets_standard(stats, limit_seconds):
        return HEADWAY_ABOVE_STANDARD
    return None


def route_fail_reason(period_reasons: list[str | None]) -> str | None:
    """Route-level fail_reason from the reasons of every scored direction and period.

    None when every one passes; otherwise the distinct reasons, sorted and joined with "; ", so a route that fails for
    both causes shows both.
    """
    reasons = sorted({r for r in period_reasons if r is not None})
    return "; ".join(reasons) if reasons else None


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


def peak_flow_count(direction_counts: list[int]) -> int:
    """Trips in the peak-flow direction: the direction with more trips in that peak.

    Equal counts in both directions (a tie) give that same count, so the tie needs no tie-break. The other direction is
    ignored. No direction at all gives 0.
    """
    return max(direction_counts, default=0)


def express_meets_standard(am_direction_counts: list[int], pm_direction_counts: list[int]) -> bool:
    """Pass when the peak-flow direction has at least 3 trips in both the AM and the PM peak."""
    return express_peak_meets_standard(peak_flow_count(am_direction_counts)) and express_peak_meets_standard(
        peak_flow_count(pm_direction_counts)
    )
