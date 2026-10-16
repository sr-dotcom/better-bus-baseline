-- test: Route 9 and Route 39 rows, and the 14 express routes, equal docs/known-answers.md
-- Offending rows: an expected row with the value the mart gave instead. Expected values are copied by hand from the
-- document: AM peak headway (section 1 and 2), span (section 3), express peak counts (section 4), Route 39 tier
-- (below standard on both dates).
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
-- section 4, Wed 2026-10-14, feed 2026-09-29: AM dir 0, AM dir 1, PM dir 0, PM dir 1, AM flow, PM flow, pass
expected_express(route_short_name, am0, am1, pm0, pm1, am_flow, pm_flow, passes) as (
    values
    ('40x', 2, 1, 0, 3, 2, 3, false),
    ('41x', 3, 0, 0, 3, 3, 3, true),
    ('46x', 3, 0, 0, 3, 3, 3, true),
    ('48x', 7, 2, 2, 6, 7, 6, true),
    ('52x', 3, 0, 0, 2, 3, 2, false),
    ('53x', 6, 0, 1, 6, 6, 6, true),
    ('61x', 6, 0, 0, 6, 6, 6, true),
    ('62x', 3, 1, 1, 3, 3, 3, true),
    ('63x', 7, 2, 1, 6, 7, 6, true),
    ('64x', 6, 0, 1, 7, 6, 7, true),
    ('74x', 2, 1, 1, 2, 2, 2, false),
    ('77x', 7, 2, 1, 6, 7, 6, true),
    ('85x', 2, 0, 1, 2, 2, 2, false),
    ('88x', 3, 0, 0, 3, 3, 3, true)
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
select 'express peak counts (am0 am1 pm0 pm1 am_flow pm_flow pass)', '2026-09-29', date '2026-10-14', e.route_short_name, null,
    cast(a.trips_direction_0 as varchar) || ' ' || cast(a.trips_direction_1 as varchar) || ' '
        || cast(p.trips_direction_0 as varchar) || ' ' || cast(p.trips_direction_1 as varchar) || ' '
        || cast(a.peak_flow_count as varchar) || ' ' || cast(p.peak_flow_count as varchar) || ' '
        || cast(c.express_pass as varchar),
    cast(e.am0 as varchar) || ' ' || cast(e.am1 as varchar) || ' ' || cast(e.pm0 as varchar) || ' '
        || cast(e.pm1 as varchar) || ' ' || cast(e.am_flow as varchar) || ' ' || cast(e.pm_flow as varchar) || ' '
        || cast(e.passes as varchar)
from expected_express e
left join express_peak_trips a
    on a.feed_version = '2026-09-29' and a.date = date '2026-10-14' and a.route_short_name = e.route_short_name
    and a.period = 'am_peak'
left join express_peak_trips p
    on p.feed_version = '2026-09-29' and p.date = date '2026-10-14' and p.route_short_name = e.route_short_name
    and p.period = 'pm_peak'
left join route_compliance c
    on c.feed_version = '2026-09-29' and c.date = date '2026-10-14' and c.route_short_name = e.route_short_name
where (a.trips_direction_0, a.trips_direction_1, p.trips_direction_0, p.trips_direction_1, a.peak_flow_count,
       p.peak_flow_count, c.express_pass)
    is distinct from (e.am0, e.am1, e.pm0, e.pm1, e.am_flow, e.pm_flow, e.passes)
union all
select 'route 39 tier', feed_version, date, route_short_name, null, tier, 'below standard'
from route_compliance
where route_short_name = '39' and day_type = 'weekday' and tier <> 'below standard'
union all
-- Route 9 and 39 run on all six dates.
select 'route has no service', feed_version, date, route_short_name, null, tier, 'service'
from route_compliance
where route_short_name in ('9', '39') and no_service_on_date;
