-- test: Route 9 and Route 39 rows equal docs/known-answers.md
-- Offending rows: an expected row with the value the mart gave instead. Expected values are copied by hand from the
-- document: AM peak headway (section 1 and 2), span (section 3), Route 39 tier (below standard on both dates).
with expected_headway(feed_version, date, route_short_name, direction_id, median_s, max_s, passes_15) as (
    values
    ('2026-09-29', date '2026-10-14', '9', 0, 900.0, 960, true),
    ('2026-09-29', date '2026-10-14', '9', 1, 900.0, 900, true),
    ('2026-09-10', date '2026-09-30', '9', 0, 900.0, 900, true),
    ('2026-09-10', date '2026-09-30', '9', 1, 900.0, 900, true),
    ('2026-09-29', date '2026-10-14', '39', 0, 2400.0, 2580, false),
    ('2026-09-29', date '2026-10-14', '39', 1, 2370.0, 2400, false),
    ('2026-09-10', date '2026-09-30', '39', 0, 2400.0, 2580, false),
    ('2026-09-10', date '2026-09-30', '39', 1, 2370.0, 2400, false)
),
expected_span(feed_version, date, route_short_name, span_start, span_end, span_pass, n_trips) as (
    values
    ('2026-09-29', date '2026-10-14', '9', '04:50:00', '25:52:00', true, 144),
    ('2026-09-10', date '2026-09-30', '9', '04:50:00', '26:01:00', true, 139),
    ('2026-09-29', date '2026-10-14', '39', '05:42:00', '25:44:00', false, 61),
    ('2026-09-10', date '2026-09-30', '39', '05:42:00', '25:44:00', false, 61)
)
select 'am_peak headway' as what, e.feed_version, e.date, e.route_short_name, e.direction_id,
    cast(h.headway_median_s as varchar) || ' / ' || cast(h.headway_max_s as varchar) || ' / ' || cast(h.passes_15 as varchar)
        as mart_value,
    cast(e.median_s as varchar) || ' / ' || cast(e.max_s as varchar) || ' / ' || cast(e.passes_15 as varchar)
        as expected_value
from expected_headway e
left join route_period_headway h
    on h.feed_version = e.feed_version and h.date = e.date and h.route_short_name = e.route_short_name
    and h.direction_id = e.direction_id and h.period = 'am_peak'
where h.headway_median_s is distinct from e.median_s or h.headway_max_s is distinct from e.max_s
   or h.passes_15 is distinct from e.passes_15
union all
select 'span', e.feed_version, e.date, e.route_short_name, null,
    s.span_start || ' / ' || s.span_end || ' / ' || cast(s.span_pass as varchar) || ' / ' || cast(s.n_trips as varchar),
    e.span_start || ' / ' || e.span_end || ' / ' || cast(e.span_pass as varchar) || ' / ' || cast(e.n_trips as varchar)
from expected_span e
left join route_span s
    on s.feed_version = e.feed_version and s.date = e.date and s.route_short_name = e.route_short_name
where s.span_start is distinct from e.span_start or s.span_end is distinct from e.span_end
   or s.span_pass is distinct from e.span_pass or s.n_trips is distinct from e.n_trips
union all
select 'route 39 tier', feed_version, date, route_short_name, null, tier, 'below standard'
from route_compliance
where route_short_name = '39' and day_type = 'weekday' and tier <> 'below standard'
union all
-- Route 9 and 39 run on all six dates.
select 'route has no service', feed_version, date, route_short_name, null, tier, 'service'
from route_compliance
where route_short_name in ('9', '39') and no_service_on_date;
