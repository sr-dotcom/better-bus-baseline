# Metric sheet

Every metric below is scored against Policy MTC-06 (Transit Service Guidelines, approved July 26, 2023). The policy text
is quoted in `data/reference/mtc06.md`. Hand-calculated answers are in `docs/known-answers.md`. The pure helpers live in
`ingest/headway.py`; the L3 marts must reproduce the helpers and the known answers.

Owner of every metric: Naga Sathwik Reddy Gona (author).

## What this measures, and what it does not

This is a schedule-based audit: it scores the timetable CATS publishes in GTFS, not the buses that ran. It does not
say whether buses were on time or whether they arrived at the frequency shown.

- Service days come only from `calendar_dates.txt` (a `service_id` runs on a date when it has a row with
  `exception_type` 1). Neither feed has `calendar.txt`, and neither has `frequencies.txt`, so every trip is an explicit
  scheduled trip and no headway is expanded from a frequency table.
- Rail (routes 501 and 510, `route_type` 0) is out of scope. Only bus routes (`route_type` 3) are scored.
- GTFS times are seconds since the start of the service day, in the agency's local clock, not timestamps. A time such as
  25:52:00 is 01:52 the next morning. No UTC conversion applies to them.
- MTC-06 3.7 words its headways as goals: "CATS will strive to provide", "As resources become available", and "Exceptions
  will be based on ridership and productivity." A route that misses a figure here is below the goal, not in breach of a
  hard rule.
- On-time performance (MTC-06 3.3) is context only in v1. It needs observed arrival times, which this audit does not
  have. See "Not measured in v1".

## Comparison dates

Each pair compares the same day of the week before and after the Oct 5, 2026 service change. The earlier date is read
from feed `2026-09-10` and the later date from feed `2026-09-29`.

| Day | Before (feed 2026-09-10) | After (feed 2026-09-29) |
| --- | --- | --- |
| Weekday | Wed 2026-09-30 | Wed 2026-10-14 |
| Saturday | Sat 2026-09-26 | Sat 2026-10-17 |
| Sunday | Sun 2026-09-27 | Sun 2026-10-18 |

## Decisions of the author (2026-10-16)

1. **Periods.** MTC-06 defines no peak hours, so these are the author's choice. Weekday AM peak 06:00-09:00, midday
   09:00-15:00, PM peak 15:00-18:00, evening 18:00-22:00. Weekend: one daytime period, 09:00-18:00.
2. **Headway statistic.** The median gap between consecutive first-stop departures in the period, per route and
   direction. The maximum gap is reported beside it. Pass or fail uses the median.
3. **Coverage.** The 15-minute standard covers both weekday peaks (AM peak and PM peak). The 30-minute standard covers AM
   peak, midday and PM peak. Express routes have no headway test; their peak trip count is decision 6.
   Weekend is report only, with no pass or fail, because MTC-06 sets no weekend frequency standard.
4. **Route verdict.** A route passes a threshold only if every scored direction passes in every covered period. Every
   local route is scored against both 15 and 30 (dual threshold). Tier is "15-min" if the route passes 15, else "30-min"
   if it passes 30, else "below standard".
5. **Span.** Start is the earliest first-stop departure and end is the latest last-stop arrival, in any direction, on the
   comparison date. Pass means start `<= 05:00:00` and end `>= 25:30:00`. Express routes are not scored: MTC-06 2.4 calls
   them "Peak hour, weekday only commuter routes".
6. **Express peak direction.** MTC-06 3.7 says "a minimum of three trips in each peak direction". Read as the
   peak-flow direction: in each peak, count only the direction with more trips, AM and PM separately. An express route
   passes when that count is at least 3 in both the AM peak and the PM peak. The other direction is ignored. Tie rule:
   if both directions have the same count, that count is the peak-flow count, so no tie-break is needed. This replaces
   the first reading, which required 3 trips in every direction of both peaks and failed every express route.
7. **No headway versus a long headway.** Fewer than 2 departures in a scored period means no headway. That period
   fails the covered standard with the reason "fewer than 2 departures in period". A real median above the limit fails with the
   reason "headway above standard". The tier metrics carry the reason as `fail_reason`, so a route that runs almost
   nothing in a window is shown differently from a route with a long headway, and neither is hidden.

## Method details

- **Departure.** The trip's first stop is the `stop_times` row with the lowest `stop_sequence`, cast to an integer. The
  trip's departure is that row's `departure_time`, in seconds since service-day start.
- **Period membership.** A departure belongs to a period if `start <= departure < end` (half-open), so 09:00:00 is
  midday and 08:59:59 is AM peak.
- **Gap.** The difference between consecutive in-period departures of the same route and direction on the date. Two trips
  at the same time give a gap of 0.
- **Median.** The median of an even number of gaps is the mean of the two middle gaps.
- **Boundary.** A gap of exactly 15:00 passes the 15-minute standard, and exactly 30:00 passes the 30-minute standard
  (the test is `median <= limit`). A median of 15:00.5 fails 15.
- **Scored direction.** A direction (`direction_id` 0 or 1) with at least one active trip on the date. A route with no
  active trip on the date has no tier; it is reported as `no_service_on_date`.
- **Fewer than 2 departures.** A direction with fewer than 2 in-period departures has no headway (decision 7). If the
  period is scored, that direction fails the period with `fail_reason` "fewer than 2 departures in period". The label covers zero
  and one departure; it does not say the route is absent all day. Route 28 direction 0 runs a trip about every 40
  minutes through the middle of the day, yet only one departs inside the AM peak window, so it gets this reason (`docs/known-answers.md`
  section 6). The check on Wed 2026-10-14 found 16 of 96 local route-directions with no AM-peak headway.
- **`fail_reason`.** On `tier_15` and `tier_30`, per route, direction and period: empty when the period passes,
  "fewer than 2 departures in period" when there is no headway, "headway above standard" when the median is above the limit. At
  route level the field lists the distinct reasons of every failing direction and period, sorted and joined with
  "; ", so a route that fails both ways shows both.
- **Express peak-flow count.** Per route and peak, the larger of the direction 0 and direction 1 counts of trips whose
  first-stop departure is in the peak (decision 6). Both direction counts are reported next to it.
- **Express routes.** In both feeds the same 14 routes have a `route_short_name` ending in `x`, and each has
  "Express" in `route_long_name`; `route_desc` is empty and `route_type` is 3 for every bus route, so it does not
  help. The rule used is `route_short_name` ends in `x`. Routes: 40x, 41x, 46x, 48x, 52x, 53x, 61x, 62x, 63x, 64x,
  74x, 77x, 85x, 88x.
- **Mixed first stops.** Trips of one route and direction can start at different stops (for example 40x direction 1
  starts at stop 32550 in the AM and 59580 in the PM). Headway is measured between first-stop departures whatever the
  stop. A route with short-turn or branch starts will show gaps that are not the gap at any one stop.
- **Refresh.** The marts are rebuilt each time a GTFS feed is loaded (`python -m ingest.load_gtfs`). v1 covers the two
  feeds in `data/sources.md` and the comparison dates above; a new feed means new comparison dates.

## Metrics

Clause column: verbatim from `data/reference/mtc06.md`, section named. Source tables are the raw tables from the loader.
Refresh for every row: as above, on each feed load. "Live" tests run now; "skipped" tests are written with their
expected values and switch on when the L3 marts exist.

| Metric | MTC-06 clause | Formula | Period | Source tables | Comparison dates | Caveat | Test |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `headway_median` | 3.7: "at least 15-minute peak service on high frequency routes and at least 30-minute service on Common/local routes and Neighborhood / Connector routes" | median of gaps between consecutive first-stop departures, per route, direction, period | AM peak, midday, PM peak, evening; weekend daytime (report only) | `raw_trips`, `raw_stop_times`, `raw_calendar_dates` | all six dates | The policy states goals ("will strive"), not a hard standard; peak hours are the author's choice; schedule, not observed service | live: `test_gaps_of_exactly_15_minutes_pass_15`, `test_median_one_second_over_15_fails`, `test_even_median_is_mean_of_two_middle_gaps`, `test_route9_after_known_answer`; skipped: `test_mart_headway_am_peak_direction_0` |
| `headway_max` | 3.7 (same clause); reported beside the median, not scored | largest gap in the same set of gaps | same as `headway_median` | same | all six dates | Not used for pass or fail: one long gap does not fail a route whose median passes | live: `test_one_long_gap_does_not_move_an_odd_median`, `test_route9_after_known_answer` |
| `tier_15` | 3.7: "at least 15-minute peak service on high frequency routes"; 2.4: "a minimum headway of 15-minutes or better" | true if the median passes `<= 15:00` for every scored direction in both weekday peaks, else false | weekday AM peak and PM peak | same | Wed 2026-09-30 and Wed 2026-10-14 | A direction with fewer than 2 departures in a peak fails with `fail_reason` "fewer than 2 departures in period"; a long median fails with "headway above standard". Local bus routes only. 15:00 passes | live: `test_gaps_of_exactly_15_minutes_pass_15`, `test_median_one_second_over_15_fails`, `test_single_departure_has_no_headway`, `test_period_boundaries_are_half_open`, `test_fail_reason_fewer_than_2_departures_for_zero_or_one_departure`, `test_fail_reason_headway_above_standard_for_a_real_long_median`, `test_fail_reason_is_none_on_the_boundary_and_below`, `test_route_fail_reason_collects_distinct_reasons`; skipped: `test_mart_headway_am_peak_direction_0`, `test_mart_tier_fail_reason_am_peak` |
| `tier_30` | 3.7: "at least 30-minute service on Common/local routes and Neighborhood / Connector routes" | true if the median passes `<= 30:00` for every scored direction in AM peak, midday and PM peak, else false. Tier label: "15-min" if `tier_15`, else "30-min" if `tier_30`, else "below standard" | weekday AM peak, midday, PM peak | same | Wed 2026-09-30 and Wed 2026-10-14 | Scored for every local route (dual threshold), even a route CATS would class as a lower tier, so route category is not assigned; 30:00 passes. `fail_reason` as for `tier_15` | live: `test_gaps_of_exactly_30_minutes_pass_30_and_fail_15`, `test_30_minutes_plus_one_second_fails_30`, `test_route39_after_known_answer_fails_30`, `test_fail_reason_headway_above_standard_for_a_real_long_median`; skipped: `test_mart_route39_tier_is_below_standard`, `test_mart_tier_fail_reason_am_peak` |
| `express_peak_trips` | 3.7: "Express and Regional Express services will have a minimum of three trips in each peak direction."; 2.4: "Express Routes - Peak hour, weekday only commuter routes" | per route and peak: count trips by direction whose first-stop departure is in the peak; peak-flow count = the larger direction count; pass if the AM peak-flow count `>= 3` and the PM peak-flow count `>= 3` | weekday AM peak, PM peak | `raw_trips`, `raw_stop_times`, `raw_calendar_dates`, `raw_routes` | Wed 2026-09-30 and Wed 2026-10-14 | "Each peak direction" is read as the peak-flow direction (decision 6); the policy does not say how to pick it. A tie gives the shared count. The other direction is ignored. Both direction counts are reported. No headway test | live: `test_express_peak_boundary`, `test_peak_flow_direction_is_the_one_with_more_trips`, `test_peak_flow_tie_gives_the_shared_count`, `test_express_boundary_in_the_peak_flow_direction`, `test_express_off_peak_direction_is_ignored`, `test_express_known_answers_64x_and_40x`; skipped: `test_mart_express_peak_flow_counts` |
| `span_start` | 3.7: "CATS Fixed Route Services will operate between 5:00 a.m. and 1:30 a.m." | earliest first-stop `departure_time` over all active trips of the route, both directions | whole service day | same | all six dates | Local routes only; express not scored. Exceptions "will be based on ridership and productivity" | skipped: `test_mart_span` |
| `span_end` | 3.7 (same clause) | latest last-stop `arrival_time` over all active trips, both directions; last stop is the highest `stop_sequence` | whole service day | same | all six dates | Times past 24:00:00 belong to the same service day (25:30:00 is 01:30 next morning) | skipped: `test_mart_span` |
| `span_pass` | 3.7 (same clause) | `span_start <= 05:00:00` and `span_end >= 25:30:00` | whole service day | same | all six dates | One late first trip fails the route even if the rest of the day is covered (Route 39 starts at 05:42:00) | live: `test_span_boundaries` (exactly 05:00:00 and 25:30:00 pass; one second either side fails); skipped: `test_mart_span` |
| `no_service_on_date` | 2.4: "Common / Local Routes - Bus routes that provide all day service on weekdays and weekends" (context); no clause sets a threshold | true if the route has zero active trips on the date; the route then has no tier and no span | whole service day | `raw_trips`, `raw_calendar_dates` | all six dates | Reported as a fact, not as a failed standard. Route 50 has no service on Sat 2026-10-17 or Sun 2026-10-18 | skipped: `test_mart_no_service_on_date_route_50` |
| `before_after_change` | 3.7 (same clauses as the headway and span metrics); 3.3: "over a course of two service changes" (context) | after minus before, same route, direction, period and day type: median change and max change in seconds, tier change, span start and end change | as the metric compared | both feeds | the three pairs above | One service change only, while 3.3 looks over two service changes. Schedule change, not an outcome for riders | skipped: `test_mart_before_after_change_route_9` |

## Not measured in v1

| Cannot be measured | Why | Internal data it would need |
| --- | --- | --- |
| On-time performance (MTC-06 3.3: "late" is 5 minutes or more after the scheduled time; the 80 percent trigger over two service changes) | The audit uses the published schedule feeds, which hold scheduled times and no observed arrivals | CATS automatic vehicle location or stop-arrival records per trip, with the scheduled time they are compared with |
| Headway as riders see it, bunching and gaps from missed trips | Scheduled spacing only | The same observed arrival records |
| Load standards (MTC-06 3.2) and passengers per hour (3.0 route monitoring) | No boardings or loads in GTFS | CATS automatic passenger count data by trip and stop |
| Peak hours | MTC-06 defines none; the periods above are the author's choice | The peak windows CATS uses internally, if any |
| Weekend frequency | MTC-06 sets no weekend headway standard; weekend headways are reported without a verdict | A weekend standard, if CATS has one beyond the policy text |
| Rail (7.5-minute peak target) | Out of scope for the bus audit | Rail schedule data are in the feed; a decision to add rail |
