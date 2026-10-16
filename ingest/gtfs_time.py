"""Parse GTFS time-of-day values."""

import re

# GTFS reference, "Field Types", Time: "H:MM:SS or HH:MM:SS", measured from "noon minus 12h" of the service day.
# Hours may exceed 24 for trips that run past midnight.
_TIME = re.compile(r"(\d{1,2}):([0-5]\d):([0-5]\d)")


def parse_gtfs_time(value: str) -> int:
    """Return seconds since the start of the service day. Raise ValueError on malformed input."""
    m = _TIME.fullmatch(value) if isinstance(value, str) else None
    if m is None:
        raise ValueError(f"malformed GTFS time {value!r}: expected H:MM:SS or HH:MM:SS")
    h, mi, s = map(int, m.groups())
    return h * 3600 + mi * 60 + s
