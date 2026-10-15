import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
        self.deadlines = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += timedelta(seconds=s)

    def fetch(self, url, timeout):
        self.fetched.append(url)
        self.deadlines.append(timeout)
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
# RFC 9110 §8.6: Content-Length is the expected body size in bytes


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


def test_empty_200_without_content_length_is_failed_and_not_saved(tmp_path):
    # GTFS Realtime reference: every FeedMessage requires a FeedHeader, so a zero-byte body is never a valid feed
    f = Fake(responses={ALERTS: (200, b"", None)})
    assert not f.collector(tmp_path).poll("alerts", ALERTS, 8)
    assert not (tmp_path / "raw").exists()
    assert rows(tmp_path) == [["2026-10-15T20:02:41Z", "alerts", "200", "0", "false"]]


# 2. Startup zone check -------------------------------------------------------


def test_startup_alerts_and_exits_nonzero_when_zone_missing(tmp_path):
    def broken():
        raise ZoneInfoNotFoundError("America/New_York")

    f = Fake()
    c = collect.Collector(tmp_path, f.clock, f.fetch, f.notify, f.sleep, zone_loader=broken)
    with pytest.raises(SystemExit) as e:
        c.run(max_rounds=1)
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
# Collector rule: alert after 3 failed polls in a row for any realtime feed.


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


def test_round_of_exactly_one_slot_is_not_an_overrun(tmp_path, caplog):
    # boundary: a round that ends exactly on the next slot (30 s) skips nothing
    f = Fake()
    c = f.collector(tmp_path)
    orig = c.run_round

    def exact():
        orig()
        f.now += timedelta(seconds=30)

    c.run_round = exact
    with caplog.at_level(logging.WARNING, logger="collector"):
        c.run(max_rounds=1)
    assert "skipped" not in caplog.text
    assert f.slept == [0.0]


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


# Total deadline per request ----------------------------------------------------
# Collector rule: 8 s total per request, connect included; elapsed >= 8 s is failed.


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


class FakeSock:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, t):
        self.timeouts.append(t)


class FakeResp:
    status = 200

    def __init__(self, clock, chunks, per_chunk):
        self.clock, self.chunks, self.per_chunk = clock, list(chunks), per_chunk
        self.length = sum(map(len, chunks))

    def getheader(self, name):
        return str(self.length)

    def read(self, n):
        if not self.chunks:
            return b""
        self.clock.t += self.per_chunk  # each chunk takes per_chunk seconds to arrive
        return self.chunks.pop(0)


class FakeConn:
    def __init__(self, clock, chunks, per_chunk, connect_time):
        self.clock, self.connect_time = clock, connect_time
        self.sock = FakeSock()
        self.resp = FakeResp(clock, chunks, per_chunk)
        self.closed = False

    def request(self, *a, **k):
        self.clock.t += self.connect_time

    def getresponse(self):
        return self.resp

    def close(self):
        self.closed = True


def fetch_with(chunks, per_chunk, connect_time=0.0):
    clock, holder = Clock(), {}

    def connect(netloc, timeout):
        holder["c"] = FakeConn(clock, chunks, per_chunk, connect_time)
        return holder["c"]

    try:
        r = collect.http_fetch("https://example.test/x.pb", 8, now=clock, connect=connect)
    except TimeoutError as e:
        r = e
    return r, holder["c"]


def test_slow_server_known_answer():
    # 4 chunks at 2 s each = 8 s elapsed against an 8 s deadline: failed
    r, conn = fetch_with([b"aa"] * 4, per_chunk=2.0)
    assert isinstance(r, TimeoutError) and conn.closed


def test_deadline_boundary_just_under_is_ok_exactly_8_is_failed():
    r, _ = fetch_with([b"ab"] * 4, per_chunk=1.99)  # 7.96 s
    assert r == (200, b"ab" * 4, 8)
    r, _ = fetch_with([b"ab"] * 4, per_chunk=2.0)  # exactly 8.0 s
    assert isinstance(r, TimeoutError)


def test_connect_time_counts_and_each_read_gets_the_time_left():
    r, _ = fetch_with([b"a"], per_chunk=0.5, connect_time=7.5)  # 8.0 s in total
    assert isinstance(r, TimeoutError)
    _, conn = fetch_with([b"a", b"b"], per_chunk=1.0, connect_time=3.0)
    assert conn.sock.timeouts == [5.0, 5.0, 4.0, 3.0]  # headers, then before each of 3 reads


def test_poll_with_deadline_failure_is_failed_and_not_saved(tmp_path):
    f = Fake(responses={ALERTS: TimeoutError("deadline exceeded")})
    assert not f.collector(tmp_path).poll("alerts", ALERTS, 8)
    assert not (tmp_path / "raw").exists() and rows(tmp_path)[0][-1] == "false"


def test_real_localhost_server_stalls_past_a_tiny_deadline():
    release = threading.Event()

    class Slow(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "10")
            self.end_headers()
            self.wfile.write(b"12345")
            self.wfile.flush()
            release.wait(5)  # stall with half the body sent

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        t0 = time.monotonic()
        with pytest.raises(TimeoutError):
            collect.http_fetch(f"http://127.0.0.1:{srv.server_port}/a.pb", 0.3)
        assert time.monotonic() - t0 < 2
    finally:
        release.set()
        srv.shutdown()
        srv.server_close()


# Clock jump ---------------------------------------------------------------------


def test_sleep_is_capped_at_one_slot_when_clock_steps_back(tmp_path):
    f = Fake()
    c = f.collector(tmp_path)
    orig = c.run_round

    def jump():
        orig()
        f.now -= timedelta(hours=1)

    c.run_round = jump
    c.run(max_rounds=1)
    assert f.slept == [30.0]  # uncapped it would sleep 1 h 30 s


# Static failure counter ---------------------------------------------------------
# Collector rule: alert on every failed static download; static and realtime counters are separate.


def test_first_static_failure_alerts(tmp_path):
    f = Fake(responses={collect.STATIC_URL: (500, b"", None)})
    f.collector(tmp_path).poll("static", collect.STATIC_URL, 60)
    assert f.sent == ["static GTFS download failed"]


def test_static_and_realtime_counters_are_separate(tmp_path):
    f = Fake(responses={collect.STATIC_URL: (500, b"", None), ALERTS: (500, b"", None)})
    c = f.collector(tmp_path)
    c.poll("alerts", ALERTS, 8)
    c.poll("alerts", ALERTS, 8)
    c.poll("static", collect.STATIC_URL, 60)  # must not count as the 3rd realtime failure
    assert f.sent == ["static GTFS download failed"]
    c.poll("alerts", ALERTS, 8)  # 3rd realtime failure: realtime alert only
    assert f.sent[1:] == ["alerts: 3 failed polls in a row"]
    assert c.fails["static"] == 1 and c.fails["alerts"] == 3


# Heartbeat ----------------------------------------------------------------------


def test_heartbeat_success_percent_known_answer(tmp_path):
    # hand-calculated: 7 of 8 polls ok = 7 / 8 = 87.5%
    f = Fake()
    c = f.collector(tmp_path)
    for _ in range(7):
        c.poll("alerts", ALERTS, 8)
    f.responses[ALERTS] = (500, b"", None)
    c.poll("alerts", ALERTS, 8)
    f.sent.clear()
    c.heartbeat()
    assert f.sent == ["heartbeat: 8 polls, 87.5% ok in the last hour"]


def test_heartbeat_with_zero_polls_has_no_percentage(tmp_path):
    f = Fake()
    f.collector(tmp_path).heartbeat()
    assert f.sent == ["heartbeat: 0 polls in the last hour"]


def test_forward_clock_jump_gives_one_heartbeat(tmp_path):
    f = Fake()
    c = f.collector(tmp_path)
    orig = c.run_round
    jumped = []

    def jump():
        orig()
        if not jumped:
            jumped.append(1)
            f.now += timedelta(hours=5)

    c.run_round = jump
    c.run(max_rounds=3)
    assert len([m for m in f.sent if m.startswith("heartbeat")]) == 1


# Per-request limits -------------------------------------------------------------


def test_round_passes_8_s_to_realtime_feeds_and_60_s_to_static(tmp_path):
    f = Fake(now=at(2026, 10, 31, 7, 0, 0))  # 03:00 New York: static is due
    f.collector(tmp_path).run_round()
    assert f.deadlines == [8, 8, 8, 60]
    assert f.fetched[-1] == collect.STATIC_URL


# Static alerts every failed day -------------------------------------------------
# Collector rule: static runs once a day, so every failed day sends an alert.


def test_static_failure_alerts_every_day(tmp_path):
    f = Fake(responses={collect.STATIC_URL: (500, b"", None)})
    c = f.collector(tmp_path)
    c.poll("static", collect.STATIC_URL, 60)  # day 1
    c.poll("static", collect.STATIC_URL, 60)  # day 2
    assert f.sent == ["static GTFS download failed"] * 2


# polls.csv format ---------------------------------------------------------------


def test_polls_csv_format_and_lf_line_endings(tmp_path):
    f = Fake()
    f.collector(tmp_path).poll("alerts", ALERTS, 8)
    raw = (tmp_path / "log" / "polls.csv").read_bytes()
    assert b"\r" not in raw
    assert raw == b"utc_time,feed,http_status,bytes,ok\n2026-10-15T20:02:41Z,alerts,200,7327,true\n"
