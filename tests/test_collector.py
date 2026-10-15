import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import collect
import pytest

FIXTURE = (Path(__file__).parent.parent / "fixtures" / "alerts.pb").read_bytes()
NY = ZoneInfo("America/New_York")
T0 = datetime(2026, 10, 15, 20, 2, 41, tzinfo=UTC)


class Fake:
    """Injected clock, sleep, fetch and ntfy: no network, no real sleeping."""

    def __init__(self, now=T0, responses=None):
        self.now = now
        self.responses = responses or {}  # url -> (status, body, length) or an exception
        self.sent = []
        self.slept = []
        self.fetched = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += timedelta(seconds=s)

    def fetch(self, url, timeout):
        self.fetched.append(url)
        r = self.responses.get(url, (200, FIXTURE, len(FIXTURE)))
        if isinstance(r, Exception):
            raise r
        return r

    def notify(self, msg):
        self.sent.append(msg)

    def collector(self, tmp_path, **kw):
        c = collect.Collector(tmp_path, self.clock, self.fetch, self.notify, self.sleep, **kw)
        c.tz = NY
        return c


def rows(tmp_path):
    lines = (tmp_path / "log" / "polls.csv").read_text().splitlines()
    assert lines[0] == "utc_time,feed,http_status,bytes,ok"
    return [line.split(",") for line in lines[1:]]


ALERTS = collect.FEEDS["alerts"]


# 1. Short response -----------------------------------------------------------


def test_short_response_is_not_saved_and_logged_not_ok(tmp_path):
    f = Fake(responses={ALERTS: (200, FIXTURE[:-1], len(FIXTURE))})  # Content-Length says 7327, body has 7326
    ok = f.collector(tmp_path).poll("alerts", ALERTS, 8)
    assert not ok
    assert not (tmp_path / "raw").exists()
    assert rows(tmp_path) == [["2026-10-15T20:02:41Z", "alerts", "200", str(len(FIXTURE) - 1), "false"]]


def test_body_exactly_content_length_is_saved(tmp_path):
    # boundary: len(body) == Content-Length is complete
    f = Fake()
    assert f.collector(tmp_path).poll("alerts", ALERTS, 8)
    assert rows(tmp_path)[0][-1] == "true"


# 2. Startup zone check -------------------------------------------------------


def test_startup_alerts_and_exits_nonzero_when_zone_missing(tmp_path):
    def broken():
        raise ZoneInfoNotFoundError("America/New_York")

    f = Fake()
    c = collect.Collector(tmp_path, f.clock, f.fetch, f.notify, f.sleep, zone_loader=broken)
    with pytest.raises(SystemExit) as e:
        c.run()
    assert e.value.code != 0
    assert len(f.sent) == 1 and "time zone" in f.sent[0]
    assert f.fetched == []  # never polled


# 3 and 4. Static download at 03:00 New York, across the DST change ------------
# America/New_York: EDT is UTC-4 until the first Sunday of November (2026-11-01, IANA tz database),
# then EST is UTC-5. So 03:00 local is 07:00Z on Oct 31 and 08:00Z on Nov 1.


def at(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=UTC)


def test_static_fires_at_0300_new_york_not_0259():
    # known answer: Oct 15 2026 is EDT, 03:00 EDT = 07:00Z
    assert not collect.static_due(at(2026, 10, 15, 6, 59, 30), None, NY)  # 02:59:30 local
    assert collect.static_due(at(2026, 10, 15, 7, 0, 0), None, NY)  # 03:00:00 local


def test_static_runs_once_per_local_day():
    assert not collect.static_due(at(2026, 10, 15, 7, 0, 30), datetime(2026, 10, 15).date(), NY)
    assert collect.static_due(at(2026, 10, 16, 7, 0, 0), datetime(2026, 10, 15).date(), NY)


def test_dst_change_moves_the_utc_instant():
    # Oct 31 (EDT): 03:00 local = 07:00Z
    assert not collect.static_due(at(2026, 10, 31, 6, 59, 59), None, NY)
    assert collect.static_due(at(2026, 10, 31, 7, 0, 0), None, NY)
    # Nov 1 (EST): 07:00Z is only 02:00 local, 03:00 local = 08:00Z
    assert not collect.static_due(at(2026, 11, 1, 7, 0, 0), None, NY)
    assert not collect.static_due(at(2026, 11, 1, 7, 59, 59), None, NY)
    assert collect.static_due(at(2026, 11, 1, 8, 0, 0), None, NY)


def test_round_downloads_static_once_and_names_it_by_utc_date(tmp_path):
    f = Fake(now=at(2026, 10, 31, 7, 0, 0))
    c = f.collector(tmp_path)
    c.run_round()
    c.run_round()
    assert f.fetched.count(collect.STATIC_URL) == 1
    assert (tmp_path / "raw" / "static" / "2026-10-31.zip").exists()


def test_round_before_0300_does_not_download_static(tmp_path):
    f = Fake(now=at(2026, 10, 31, 6, 59, 30))
    f.collector(tmp_path).run_round()
    assert collect.STATIC_URL not in f.fetched


# 5. Alert after exactly 3 failed polls in a row -------------------------------
# Collector rule: alert after 3 failed polls in a row for any feed.


def failing(tmp_path):
    f = Fake(responses={ALERTS: (500, b"", None)})
    return f, f.collector(tmp_path)


def test_two_failures_no_alert_three_alert(tmp_path):
    f, c = failing(tmp_path)
    c.poll("alerts", ALERTS, 8)
    c.poll("alerts", ALERTS, 8)
    assert f.sent == []
    c.poll("alerts", ALERTS, 8)
    assert f.sent == ["alerts: 3 failed polls in a row"]
    c.poll("alerts", ALERTS, 8)  # 4th: no repeat alert
    assert len(f.sent) == 1


def test_success_resets_the_count(tmp_path):
    f, c = failing(tmp_path)
    c.poll("alerts", ALERTS, 8)
    c.poll("alerts", ALERTS, 8)
    f.responses.clear()
    assert c.poll("alerts", ALERTS, 8)
    f.responses[ALERTS] = (500, b"", None)
    c.poll("alerts", ALERTS, 8)
    c.poll("alerts", ALERTS, 8)
    assert f.sent == []  # 2 + 2, never 3 in a row


def test_counts_are_per_feed(tmp_path):
    f, c = failing(tmp_path)
    other = collect.FEEDS["vehicle_positions"]
    for _ in range(2):
        c.poll("alerts", ALERTS, 8)
    c.poll("vehicle_positions", other, 8)
    assert f.sent == []


# 6. UTC paths, and a failed poll never crashes the loop -----------------------


def test_saved_path_and_name_are_utc(tmp_path):
    f = Fake(now=datetime(2026, 10, 15, 23, 5, 9, tzinfo=UTC))  # 19:05:09 in New York
    f.collector(tmp_path).poll("alerts", ALERTS, 8)
    saved = tmp_path / "raw" / "alerts" / "2026-10-15" / "230509Z.pb"
    assert saved.read_bytes() == FIXTURE  # unchanged


@pytest.mark.parametrize("err", [TimeoutError(), OSError("boom"), ValueError("x")])
def test_fetch_exception_is_a_failed_poll_not_a_crash(tmp_path, err):
    f = Fake(responses={ALERTS: err})
    assert not f.collector(tmp_path).poll("alerts", ALERTS, 8)
    assert rows(tmp_path)[0][2:] == ["0", "0", "false"]


def test_loop_survives_failures_and_keeps_schedule(tmp_path):
    f = Fake(responses={url: TimeoutError() for url in collect.FEEDS.values()})
    c = f.collector(tmp_path)
    c.run(max_rounds=3)
    assert len(rows(tmp_path)) == 9  # 3 feeds x 3 rounds
    assert f.slept == [30.0, 30.0, 30.0]  # fixed schedule: the fake round takes 0 s


def test_overrun_skips_to_next_slot_and_logs(tmp_path, caplog):
    f = Fake()
    c = f.collector(tmp_path)
    orig = c.run_round

    def slow():
        orig()
        f.now += timedelta(seconds=35)  # round ends 5 s into the next slot

    c.run_round = slow
    with caplog.at_level(logging.WARNING, logger="collector"):
        c.run(max_rounds=1)
    assert "skipped 1 slot" in caplog.text
    assert f.slept == [25.0]  # next slot is 60 s after start, 35 s have passed


def test_empty_topic_warns_and_does_not_crash(caplog):
    with caplog.at_level(logging.WARNING, logger="collector"):
        send = collect.make_ntfy("")
    send("hello")  # no-op, no network
    assert "NTFY_TOPIC is empty" in caplog.text


def test_heartbeat_after_one_hour(tmp_path):
    f = Fake()
    c = f.collector(tmp_path)
    c.run(max_rounds=121)  # 120 slots of 30 s = 1 h
    beats = [m for m in f.sent if m.startswith("heartbeat")]
    assert len(beats) == 1 and "100.0% ok" in beats[0]


def test_start_after_0300_waits_for_next_day(tmp_path):
    f = Fake()  # 16:02 in New York
    f.collector(tmp_path).run(max_rounds=1)
    assert collect.STATIC_URL not in f.fetched
