"""GTFS-Realtime collector. Standard library only.

One loop, one thread. Every 30 s it polls three feeds in sequence and saves each
response unchanged under DATA_DIR/raw. Static GTFS is fetched once a day at 03:00
America/New_York. Every file name and log timestamp is UTC.
"""

import csv
import http.client
import logging
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://gtfsrealtime.ridetransit.org"
FEEDS = {
    "trip_updates": f"{BASE}/GTFSRealTime/TripUpdate/TripUpdates.pb",
    "vehicle_positions": f"{BASE}/GTFSRealTime/Vehicle/VehiclePositions.pb",
    "alerts": f"{BASE}/GTFSRealTime/Alert/Alerts.pb",
}
STATIC_URL = f"{BASE}/GTFSStatic/api/GTFSDownload/GTFS.zip"

SLOT = timedelta(seconds=30)
FEED_TIMEOUT = 8  # seconds in total per request; 3 x 8 = 24 s fits the 30 s slot
STATIC_TIMEOUT = 60  # total seconds; the zip is large and is fetched when no buses run
ALERT_AFTER = 3  # failed realtime polls in a row
STATIC_ALERT_AFTER = 1  # the static download runs once a day: alert on the first failure
STATIC_AT = dtime(3, 0)  # local time in ZONE
ZONE = "America/New_York"
HEARTBEAT = timedelta(hours=1)

log = logging.getLogger("collector")


def utc_stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def static_due(now: datetime, last_done: date | None, tz: ZoneInfo) -> bool:
    """True once local time has reached STATIC_AT and today's download has not been tried."""
    local = now.astimezone(tz)
    return local.time() >= STATIC_AT and last_done != local.date()


def http_fetch(url: str, deadline: float, now=time.monotonic, connect=None) -> tuple[int, bytes, int | None]:
    """GET url and return (status, body, content_length) within a total deadline in seconds.

    The clock starts before the connection is opened. Every blocking step gets the time
    that is left, not a fresh timeout. Elapsed >= deadline is a failure (TimeoutError),
    even if the last byte just arrived. A short body is returned, not raised.

    Bounded: TCP connect, TLS handshake, response headers, each body read.
    NOT bounded: the DNS lookup inside connect (getaddrinfo has no timeout in the
    standard library), so a hung resolver can overrun the deadline.
    """
    start = now()

    def left() -> float:
        remaining = deadline - (now() - start)
        if remaining <= 0:
            raise TimeoutError("deadline exceeded")
        return remaining

    u = urllib.parse.urlsplit(url)
    connect = connect or (http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection)
    conn = connect(u.netloc, timeout=left())
    try:
        conn.request("GET", u.path or "/", headers={"User-Agent": "better-bus-baseline-collector"})
        sock = conn.sock  # kept: http.client sets conn.sock to None once the body is read
        sock.settimeout(left())
        resp = conn.getresponse()
        length = resp.getheader("Content-Length")
        chunks = []
        while True:
            sock.settimeout(left())
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
        left()  # finishing at or after the deadline is a failed poll
        return resp.status, b"".join(chunks), int(length) if length else None
    finally:
        conn.close()


def make_ntfy(topic: str):
    """Return send(message). The topic is never logged; errors log the class name only."""
    if not topic:
        log.warning("NTFY_TOPIC is empty: notifications are off, collecting continues")
        return lambda message: None

    def send(message: str) -> None:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=message.encode(), method="POST")
        try:
            urllib.request.urlopen(req, timeout=FEED_TIMEOUT).close()
        except Exception as e:  # noqa: BLE001 - a failed notification must never stop collecting
            log.warning("ntfy send failed: %s", type(e).__name__)

    return send


class Collector:
    def __init__(self, data_dir, clock, fetch, notify, sleep, zone_loader=lambda: ZoneInfo(ZONE)):
        self.data = Path(data_dir)
        self.clock, self.fetch, self.notify, self.sleep = clock, fetch, notify, sleep
        self.zone_loader = zone_loader
        self.tz = None
        self.fails = {}  # feed -> consecutive failed polls
        self.last_static = None  # local date of the last static attempt
        self.hb_polls = self.hb_ok = 0

    def start_check(self) -> None:
        try:
            self.tz = self.zone_loader()
        except Exception as e:
            log.error("cannot load time zone %s: %s", ZONE, type(e).__name__)
            self.notify(f"collector cannot start: time zone {ZONE} failed to load")
            raise SystemExit(1) from e

    def poll(self, feed: str, url: str, timeout: float) -> bool:
        t = self.clock()
        status, body, length = 0, b"", None
        try:
            status, body, length = self.fetch(url, timeout)
        except Exception as e:  # noqa: BLE001 - any fetch error is a failed poll, never a crash
            log.warning("%s fetch failed: %s", feed, type(e).__name__)
        short = length is not None and len(body) < length
        ok = status == 200 and len(body) > 0 and not short
        if ok:
            try:
                self.save(feed, t, body)
            except OSError as e:
                log.error("%s save failed: %s", feed, type(e).__name__)
                ok = False
        if short:
            log.warning("%s short response: %d of %d bytes", feed, len(body), length)
        self.append_log(t, feed, status, len(body), ok)
        self.track(feed, ok)
        return ok

    def save(self, feed: str, t: datetime, body: bytes) -> None:
        if feed == "static":
            path = self.data / "raw" / "static" / f"{t:%Y-%m-%d}.zip"
        else:
            path = self.data / "raw" / feed / f"{t:%Y-%m-%d}" / f"{t:%H%M%S}Z.pb"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def append_log(self, t: datetime, feed: str, status: int, size: int, ok: bool) -> None:
        path = self.data / "log" / "polls.csv"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            with path.open("a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["utc_time", "feed", "http_status", "bytes", "ok"])
                w.writerow([utc_stamp(t), feed, status, size, str(ok).lower()])
        except OSError as e:
            log.error("polls.csv write failed: %s", type(e).__name__)

    def track(self, feed: str, ok: bool) -> None:
        self.hb_polls += 1
        self.hb_ok += ok
        self.fails[feed] = 0 if ok else self.fails.get(feed, 0) + 1
        limit = STATIC_ALERT_AFTER if feed == "static" else ALERT_AFTER
        if self.fails[feed] == limit:  # once per streak, not on every further failure
            if feed == "static":
                self.notify("static GTFS download failed")
            else:
                self.notify(f"{feed}: {limit} failed polls in a row")

    def run_round(self) -> None:
        for feed, url in FEEDS.items():
            self.poll(feed, url, FEED_TIMEOUT)
        now = self.clock()
        if static_due(now, self.last_static, self.tz):
            self.last_static = now.astimezone(self.tz).date()
            self.poll("static", STATIC_URL, STATIC_TIMEOUT)

    def heartbeat(self) -> None:
        pct = 100 * self.hb_ok / self.hb_polls if self.hb_polls else 0
        self.notify(f"heartbeat: {self.hb_polls} polls, {pct:.1f}% ok in the last hour")
        self.hb_polls = self.hb_ok = 0

    def run(self, max_rounds: int | None = None) -> None:
        self.start_check()
        self.notify("collector started")
        slot = self.clock()
        if static_due(slot, None, self.tz):  # started after 03:00: wait for tomorrow's 03:00
            self.last_static = slot.astimezone(self.tz).date()
        next_hb = slot + HEARTBEAT
        rounds = 0
        while max_rounds is None or rounds < max_rounds:
            try:
                self.run_round()
            except Exception:
                log.exception("round failed")
            rounds += 1
            now = self.clock()
            if now >= next_hb:
                self.heartbeat()
                next_hb += HEARTBEAT
            slot += SLOT
            if now > slot:
                skipped = math.ceil((now - slot) / SLOT)
                slot += skipped * SLOT
                log.warning("round overran its slot: skipped %d slot(s)", skipped)
            # never sleep longer than one slot, even if the clock stepped backwards
            self.sleep(min(SLOT.total_seconds(), max(0.0, (slot - now).total_seconds())))


def main() -> None:
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    Collector(
        os.environ.get("DATA_DIR", "/data"),
        clock=lambda: datetime.now(UTC),
        fetch=http_fetch,
        notify=make_ntfy(os.environ.get("NTFY_TOPIC", "")),
        sleep=time.sleep,
    ).run()


if __name__ == "__main__":
    sys.exit(main())
