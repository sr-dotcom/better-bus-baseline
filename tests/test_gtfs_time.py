import pytest

from ingest.gtfs_time import parse_gtfs_time


# GTFS reference, Field Types, Time: H:MM:SS or HH:MM:SS, hours may exceed 24.
# Hand calculation: 25*3600 + 30*60 = 90000 + 1800 = 91800.
def test_after_midnight_known_answer():
    assert parse_gtfs_time("25:30:00") == 91800


# 5*3600 = 18000
def test_morning_known_answer():
    assert parse_gtfs_time("05:00:00") == 18000


# Single-digit hour is allowed (H:MM:SS): 5*3600 + 7*60 + 9 = 18429
def test_single_digit_hour():
    assert parse_gtfs_time("5:07:09") == 18429


# Boundaries: start of day, and the last second of the 24:00 hour.
def test_boundaries():
    assert parse_gtfs_time("00:00:00") == 0
    assert parse_gtfs_time("24:00:00") == 86400
    assert parse_gtfs_time("23:59:59") == 86399


@pytest.mark.parametrize(
    "bad", ["", "5", "05:00", "05:60:00", "05:00:60", "5:0:00", "-1:00:00", "05:00:00 ", "aa:bb:cc", "100:00:00"]
)
def test_malformed_rejected(bad):
    with pytest.raises(ValueError, match="malformed GTFS time"):
        parse_gtfs_time(bad)


def test_non_string_rejected():
    with pytest.raises(ValueError, match="malformed GTFS time"):
        parse_gtfs_time(None)
