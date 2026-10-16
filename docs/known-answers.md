# Known answers

Hand-checkable numbers for the metrics in `docs/metrics.md`. Everything here comes from the raw tables (`raw_trips`,
`raw_stop_times`, `raw_calendar_dates`) with plain SQL and the pure helper `ingest/headway.py`; no mart is involved.
The marts land in L3 and must reproduce these numbers. Source feeds: `data/sources.md`.

## Method in one paragraph

A trip belongs to a day if its `service_id` has a `calendar_dates.txt` row for that date with `exception_type` 1
(these feeds have no `calendar.txt`). The trip's first stop is the row with the lowest `stop_sequence` (cast to
integer); its `departure_time` is the trip's departure. AM peak is `06:00:00 <= departure < 09:00:00`. Gaps are
between consecutive departures of one route and direction. The median of an even number of gaps is the mean of the
two middle gaps. The 15-minute standard passes when the median is `<= 15:00` (MTC-06 3.7); span passes when the
earliest first-stop departure is `<= 05:00:00` and the latest last-stop arrival is `>= 25:30:00` (MTC-06 3.7).

SQL used for the departures (DuckDB; `:feed`, `:route`, `:dir`, `:ymd` are parameters, `:ymd` as `YYYYMMDD`):

```sql
select t.trip_id, t.service_id, s.stop_id, s.stop_sequence, s.departure_time
from raw_trips t
join raw_stop_times s on s.trip_id = t.trip_id and s.feed_version = t.feed_version
where t.feed_version = :feed and t.route_id = :route and t.direction_id = :dir
  and t.service_id in (select service_id from raw_calendar_dates
                       where feed_version = :feed and date = :ymd and exception_type = '1')
qualify row_number() over (partition by t.trip_id order by cast(s.stop_sequence as integer)) = 1
order by cast(s.stop_sequence as integer), s.departure_time, t.trip_id;
```

For span end, the same query with `arrival_time` and the last stop (`stop_sequence` descending) per trip.

## How to check a number in the zip

Each table row names a `trip_id`, `stop_id` and time. To see the source row:

```
unzip -p data/raw/mdb-2265-202609290116.zip stop_times.txt | grep '^5603724,'
```

The first line printed for that trip (`stop_sequence` 1) is the first-stop row; the highest `stop_sequence` line is
the last-stop row. The route and direction come from `trips.txt` (`route_id`, `direction_id`), and the date from
`calendar_dates.txt` (`service_id`, `date`). Times past 24:00:00 are the next calendar day, kept as read.

## 1. Route 9 (Central Avenue), Wed AM peak, direction 0

### Route 9, after feed

Feed `2026-09-29` (`mdb-2265-202609290116.zip`), Wed 2026-10-14, route 9, direction 0, AM peak 06:00:00 <= departure < 09:00:00. 12 trips, 11 gaps.

| # | trip_id | stop_id | stop_sequence | departure_time | gap to previous (m:ss) |
| --- | --- | --- | --- | --- | --- |
| 1 | 5603724 | 00285 | 1 | 06:05:00 |  |
| 2 | 5604043 | 00285 | 1 | 06:20:00 | 15:00 |
| 3 | 5603974 | 00285 | 1 | 06:35:00 | 15:00 |
| 4 | 5603975 | 00285 | 1 | 06:50:00 | 15:00 |
| 5 | 5603976 | 00285 | 1 | 07:05:00 | 15:00 |
| 6 | 5603977 | 00285 | 1 | 07:20:00 | 15:00 |
| 7 | 5603978 | 00285 | 1 | 07:36:00 | 16:00 |
| 8 | 5603979 | 00285 | 1 | 07:51:00 | 15:00 |
| 9 | 5603980 | 00285 | 1 | 08:06:00 | 15:00 |
| 10 | 5603981 | 00285 | 1 | 08:21:00 | 15:00 |
| 11 | 5603982 | 00285 | 1 | 08:36:00 | 15:00 |
| 12 | 5603983 | 00285 | 1 | 08:51:00 | 15:00 |

Gaps: 15:00, 15:00, 15:00, 15:00, 15:00, 16:00, 15:00, 15:00, 15:00, 15:00, 15:00. Median 15:00, max 16:00. Passes the 15-minute standard (passes the 30-minute standard). For comparison, direction 1: median 15:00, max 15:00.

### Route 9, before feed

Feed `2026-09-10` (`mdb-2265-202609100002.zip`), Wed 2026-09-30, route 9, direction 0, AM peak 06:00:00 <= departure < 09:00:00. 12 trips, 11 gaps.

| # | trip_id | stop_id | stop_sequence | departure_time | gap to previous (m:ss) |
| --- | --- | --- | --- | --- | --- |
| 1 | 5438210 | 00285 | 1 | 06:05:00 |  |
| 2 | 5438529 | 00285 | 1 | 06:20:00 | 15:00 |
| 3 | 5438460 | 00285 | 1 | 06:35:00 | 15:00 |
| 4 | 5438461 | 00285 | 1 | 06:50:00 | 15:00 |
| 5 | 5438462 | 00285 | 1 | 07:05:00 | 15:00 |
| 6 | 5438463 | 00285 | 1 | 07:20:00 | 15:00 |
| 7 | 5438464 | 00285 | 1 | 07:35:00 | 15:00 |
| 8 | 5438465 | 00285 | 1 | 07:50:00 | 15:00 |
| 9 | 5438466 | 00285 | 1 | 08:05:00 | 15:00 |
| 10 | 5438467 | 00285 | 1 | 08:20:00 | 15:00 |
| 11 | 5438468 | 00285 | 1 | 08:35:00 | 15:00 |
| 12 | 5438469 | 00285 | 1 | 08:50:00 | 15:00 |

Gaps: 15:00, 15:00, 15:00, 15:00, 15:00, 15:00, 15:00, 15:00, 15:00, 15:00, 15:00. Median 15:00, max 15:00. Passes the 15-minute standard (passes the 30-minute standard). For comparison, direction 1: median 15:00, max 15:00.

**Did the headway change?** The median did not change: 15:00 before and 15:00 after, so
Route 9 passes the 15-minute standard on both dates. The max gap changed from 15:00 to 16:00:
after the Oct 5 change, trips 5603978 onward start one minute later than the same slot in the before feed
(07:36:00 against 07:35:00), which opens one 16:00 gap at 07:20:00 to 07:36:00. The timetable is otherwise the same
15-minute pattern.

## 2. A failing route: route 39

How it was chosen: of the 48 local bus routes (route_type 3, not express, so 14 express routes and the 2 rail routes are
out), keep those whose direction 0 has at least 5 AM-peak departures on Wed 2026-10-14 (so the median is taken over
at least 4 gaps) and a median gap above 30:00; 7 routes qualify; route 39 has the largest median.
It also fails in direction 1, so it fails whichever direction is read.

### Route 39, after feed (failing route)

Feed `2026-09-29` (`mdb-2265-202609290116.zip`), Wed 2026-10-14, route 39, direction 0, AM peak 06:00:00 <= departure < 09:00:00. 5 trips, 4 gaps.

| # | trip_id | stop_id | stop_sequence | departure_time | gap to previous (m:ss) |
| --- | --- | --- | --- | --- | --- |
| 1 | 5603310 | 45322 | 1 | 06:15:00 |  |
| 2 | 5603311 | 45322 | 1 | 06:53:00 | 38:00 |
| 3 | 5603312 | 45322 | 1 | 07:28:00 | 35:00 |
| 4 | 5603308 | 45322 | 1 | 08:10:00 | 42:00 |
| 5 | 5603313 | 45322 | 1 | 08:53:00 | 43:00 |

Gaps: 38:00, 35:00, 42:00, 43:00. Median 40:00, max 43:00. Fails the 15-minute standard (fails the 30-minute standard). For comparison, direction 1: median 39:30, max 40:00.

### Route 39, before feed

Feed `2026-09-10` (`mdb-2265-202609100002.zip`), Wed 2026-09-30, route 39, direction 0, AM peak 06:00:00 <= departure < 09:00:00. 5 trips, 4 gaps.

| # | trip_id | stop_id | stop_sequence | departure_time | gap to previous (m:ss) |
| --- | --- | --- | --- | --- | --- |
| 1 | 5439398 | 45322 | 1 | 06:15:00 |  |
| 2 | 5439399 | 45322 | 1 | 06:53:00 | 38:00 |
| 3 | 5439400 | 45322 | 1 | 07:28:00 | 35:00 |
| 4 | 5439396 | 45322 | 1 | 08:10:00 | 42:00 |
| 5 | 5439401 | 45322 | 1 | 08:53:00 | 43:00 |

Gaps: 38:00, 35:00, 42:00, 43:00. Median 40:00, max 43:00. Fails the 15-minute standard (fails the 30-minute standard). For comparison, direction 1: median 39:30, max 40:00.

Route 39 did not change between the feeds on this window: median 40:00 before, 40:00 after.

## 3. Span

Pass needs start `<= 05:00:00` and end `>= 25:30:00`, any direction, all trips active on the date.

| feed | date | route | earliest first-stop departure | latest last-stop arrival | start <= 05:00:00 | end >= 25:30:00 | span | trips counted |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 | 2026-10-14 | 9 | 04:50:00 | 25:52:00 | yes | yes | **pass** | 144 |
| 2026-09-10 | 2026-09-30 | 9 | 04:50:00 | 26:01:00 | yes | yes | **pass** | 139 |
| 2026-09-29 | 2026-10-14 | 39 | 05:42:00 | 25:44:00 | no | yes | **fail** | 61 |
| 2026-09-10 | 2026-09-30 | 39 | 05:42:00 | 25:44:00 | no | yes | **fail** | 61 |

Rows used (every trip that equals the start or the end value):

| feed | date | route | role | trip_id | stop_id | stop_sequence | time | direction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 | 2026-10-14 | 9 | start | 5604037 | 00285 | 1 | departure_time 04:50:00 | direction 0 |
| 2026-09-29 | 2026-10-14 | 9 | end | 5664748 | 00285 | 35 | arrival_time 25:52:00 | direction 1 |
| 2026-09-10 | 2026-09-30 | 9 | start | 5438523 | 00285 | 1 | departure_time 04:50:00 | direction 0 |
| 2026-09-10 | 2026-09-30 | 9 | end | 5438196 | 00285 | 35 | arrival_time 26:01:00 | direction 1 |
| 2026-09-29 | 2026-10-14 | 39 | start | 5603309 | 45322 | 1 | departure_time 05:42:00 | direction 0 |
| 2026-09-29 | 2026-10-14 | 39 | end | 5603337 | 60230 | 45 | arrival_time 25:44:00 | direction 0 |
| 2026-09-10 | 2026-09-30 | 39 | start | 5439397 | 45322 | 1 | departure_time 05:42:00 | direction 0 |
| 2026-09-10 | 2026-09-30 | 39 | end | 5439425 | 60230 | 45 | arrival_time 25:44:00 | direction 0 |

Route 9 passes on both dates: it starts at 04:50:00 and ends after 25:30:00. Route 39 fails on both dates
because its first trip leaves at 05:42:00, after 05:00:00, although its last trip arrives after 25:30:00.

## 4. Express peak trips (MTC-06 3.7: "a minimum of three trips in each peak direction")

Express routes are the 14 route_ids whose `route_short_name` ends in `x`. Peaks are AM `06:00:00 <= t < 09:00:00` and
PM `15:00:00 <= t < 18:00:00`. Rule: in each peak, count the trips in the peak-flow direction, which is the direction
with more trips in that peak (AM and PM are decided separately). The route passes when that count is at least 3 in
both peaks. The other direction is ignored. If both directions have the same count, that count is the peak-flow count
and no tie-break is needed. Weekday only; express routes have no headway test.

Route 64x, Wed 2026-10-14, feed `2026-09-29`, first-stop departures inside a peak:

| direction | peak | trip_id | stop_id | stop_sequence | departure_time |
| --- | --- | --- | --- | --- | --- |
| 0 | am_peak | 5617128 | 37480 | 1 | 06:15:00 |
| 0 | am_peak | 5617129 | 37480 | 1 | 06:45:00 |
| 0 | am_peak | 5617130 | 37480 | 1 | 07:10:00 |
| 0 | am_peak | 5617131 | 37480 | 1 | 07:35:00 |
| 0 | am_peak | 5617132 | 37480 | 1 | 08:00:00 |
| 0 | am_peak | 5617133 | 37480 | 1 | 08:25:00 |
| 0 | pm_peak | 5617139 | 37480 | 1 | 15:10:00 |
| 1 | pm_peak | 5617120 | 59580 | 1 | 15:20:00 |
| 1 | pm_peak | 5617121 | 59580 | 1 | 15:45:00 |
| 1 | pm_peak | 5617122 | 59580 | 1 | 16:10:00 |
| 1 | pm_peak | 5617123 | 59580 | 1 | 16:35:00 |
| 1 | pm_peak | 5617124 | 59580 | 1 | 17:00:00 |
| 1 | pm_peak | 5617125 | 59580 | 1 | 17:25:00 |
| 1 | pm_peak | 5617126 | 59580 | 1 | 17:55:00 |

Counts: direction 0 am_peak = 6; direction 0 pm_peak = 1; direction 1 am_peak = 0; direction 1 pm_peak = 7.

64x passes: AM peak-flow direction is 0 with 6 trips, PM peak-flow direction is 1 with 7 trips.

Route 40x, Wed 2026-10-14, feed `2026-09-29`, first-stop departures inside a peak:

| direction | peak | trip_id | stop_id | stop_sequence | departure_time |
| --- | --- | --- | --- | --- | --- |
| 0 | am_peak | 5604875 | 11990 | 1 | 06:47:00 |
| 0 | am_peak | 5604884 | 11990 | 1 | 07:47:00 |
| 1 | am_peak | 5604840 | 32550 | 1 | 06:14:00 |
| 1 | pm_peak | 5604843 | 59580 | 1 | 16:05:00 |
| 1 | pm_peak | 5604853 | 59580 | 1 | 17:00:00 |
| 1 | pm_peak | 5604863 | 59580 | 1 | 17:55:00 |

Counts: direction 0 am_peak = 2; direction 0 pm_peak = 0; direction 1 am_peak = 1; direction 1 pm_peak = 3.

40x fails: AM peak-flow direction is 0 with 2 trips (its 05:47:00 trip is before 06:00:00), so the AM count is below 3;
the PM peak-flow count is 3 (direction 1), which would pass on its own.

All 14 express routes, Wed 2026-10-14, feed `2026-09-29` (first-stop departures by direction in each peak):

| route | AM peak, direction 0 | AM peak, direction 1 | PM peak, direction 0 | PM peak, direction 1 | AM peak-flow count | PM peak-flow count | express pass |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 40x | 2 | 1 | 0 | 3 | 2 | 3 | fail |
| 41x | 3 | 0 | 0 | 3 | 3 | 3 | pass |
| 46x | 3 | 0 | 0 | 3 | 3 | 3 | pass |
| 48x | 7 | 2 | 2 | 6 | 7 | 6 | pass |
| 52x | 3 | 0 | 0 | 2 | 3 | 2 | fail |
| 53x | 6 | 0 | 1 | 6 | 6 | 6 | pass |
| 61x | 6 | 0 | 0 | 6 | 6 | 6 | pass |
| 62x | 3 | 1 | 1 | 3 | 3 | 3 | pass |
| 63x | 7 | 2 | 1 | 6 | 7 | 6 | pass |
| 64x | 6 | 0 | 1 | 7 | 6 | 7 | pass |
| 74x | 2 | 1 | 1 | 2 | 2 | 2 | fail |
| 77x | 7 | 2 | 1 | 6 | 7 | 6 | pass |
| 85x | 2 | 0 | 1 | 2 | 2 | 2 | fail |
| 88x | 3 | 0 | 0 | 3 | 3 | 3 | pass |

## 5. No service on a date

Route 50 (URP/CIC) has trips on the weekday date and none on the weekend dates after the change. Active trips by date
(feed `2026-09-29`, `service_id` joined to `calendar_dates.txt` as above):

| date | route | active trips |
| --- | --- | --- |
| Wed 2026-10-14 | 50 | 4 |
| Sat 2026-10-17 | 50 | 0 |
| Sun 2026-10-18 | 50 | 0 |

The 4 trips on Wed 2026-10-14 are 5604787, 5604791, 5604761, 5604768. For the two weekend dates the join returns no rows, so the
metric reports "no service on date" for route 50, not a failed standard.

## 6. Fail reasons on a scored period

A scored period that fails carries a reason. "fewer than 2 departures in period" covers none or one
departure, so there is no headway to compare. "headway above standard" means a real median above the limit. Wed 2026-10-14,
feed `2026-09-29`, direction 0, AM peak (scored against both 15:00 and 30:00):

| route | AM-peak departures | median | fail reason against 15 | fail reason against 30 |
| --- | --- | --- | --- | --- |
| 35 | 0 | none | fewer than 2 departures in period | fewer than 2 departures in period |
| 28 | 1 | none | fewer than 2 departures in period | fewer than 2 departures in period |
| 39 | 5 | 40:00 | headway above standard | headway above standard |

Route 35 has no AM-peak departure; every direction-0 trip it runs that day (the AM-peak flag shows none):

| trip_id | stop_id | stop_sequence | departure_time | in AM peak |
| --- | --- | --- | --- | --- |
| 5606243 | 60531 | 1 | 05:15:00 | no |
| 5606244 | 45726 | 1 | 05:40:00 | no |
| 5606245 | 45726 | 1 | 17:50:00 | no |

Route 28 has exactly one AM-peak departure, so no gap exists; every direction-0 trip it runs that day:

| trip_id | stop_id | stop_sequence | departure_time | in AM peak |
| --- | --- | --- | --- | --- |
| 5604557 | 30190 | 1 | 08:22:00 | yes |
| 5604560 | 30190 | 1 | 09:01:00 | no |
| 5604565 | 30190 | 1 | 09:41:00 | no |
| 5604569 | 30190 | 1 | 10:21:00 | no |
| 5604575 | 30190 | 1 | 11:00:00 | no |
| 5604581 | 30190 | 1 | 11:40:00 | no |
| 5604588 | 30190 | 1 | 12:20:00 | no |
| 5604591 | 30190 | 1 | 13:00:00 | no |
| 5604598 | 30190 | 1 | 13:40:00 | no |
| 5604604 | 30190 | 1 | 14:22:00 | no |
| 5604605 | 30190 | 1 | 15:00:00 | no |
| 5604612 | 30190 | 1 | 15:30:00 | no |
| 5604619 | 30190 | 1 | 16:07:00 | no |
| 5604622 | 30190 | 1 | 17:00:00 | no |
| 5604628 | 30190 | 1 | 17:54:00 | no |
| 5604635 | 30190 | 1 | 18:40:00 | no |

Route 39 is the section 2 route: it has a real median above both limits.
